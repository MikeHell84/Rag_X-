"""Tareas asíncronas de ingesta.

Pipeline (ver README, sección 3):

- ingest_document: extrae texto -> fragmenta -> persiste chunks y lanza un
  chord() para embeder cada lote en paralelo. El callback finalize_ingestion
  cierra el flujo. El servidor web NUNCA ejecuta esto: lo delega a la cola.
- embed_chunks_batch: llama a OpenAI con retries + exponential backoff y
  actualiza pgvector + Whoosh. Ante fallo definitivo devuelve {"ok": False}
  en lugar de reventar el chord.
- Retries: @shared_task(bind=True, max_retries=...) + countdown exponencial.
"""

import random
from typing import List

from celery import chord, shared_task
from django.shortcuts import get_object_or_404

from core.bm25 import get_bm25_index
from core.chunking import HybridChunker, SemanticDriftGuard, extract_text
from core.embeddings import EmbeddingService, get_embedding_service
from core.providers import is_transient_error
from core.vector_store import delete_embeddings, upsert_embedding, vector_dim

from .models import Chunk, Document


def exponential_backoff(retries: int, base: float = 2.0, cap: float = 120.0) -> float:
    return min(base ** (retries + 1), cap) + random.uniform(0, 0.5)


@shared_task(bind=True, max_retries=3, acks_late=True)
def ingest_document(self, document_id: int) -> dict:
    document = get_object_or_404(Document, pk=document_id)
    if document.status == Document.Status.READY:
        return {"document_id": document_id, "skipped": True}

    document.status = Document.Status.PROCESSING
    document.error_message = ""
    document.save(update_fields=["status", "error_message", "updated_at"])

    try:
        text, page_hints = extract_text(document.file.path, document.source_type)
        chunker = _build_chunker(document)
        candidates = chunker.chunk_text(text, default_section=document.title)

        Chunk.objects.filter(document=document).delete()
        get_bm25_index().delete_document(document_id)

        chunks = Chunk.objects.bulk_create(
            Chunk(
                document=document,
                index=i,
                section=candidate.section,
                page=candidate.page,
                content=candidate.content,
                token_count=candidate.token_count,
            )
            for i, candidate in enumerate(candidates)
        )
        document.status = Document.Status.CHUNKED
        document.total_chunks = len(chunks)
        document.total_tokens = sum(c.token_count for c in chunks)
        document.save(update_fields=["status", "total_chunks", "total_tokens", "updated_at"])

        batch_ids = [
            [chunk.id for chunk in chunks[i : i + _batch_size()]]
            for i in range(0, len(chunks), _batch_size())
        ]
        if not batch_ids:
            document.status = Document.Status.FAILED
            document.error_message = (
                "No se pudo extraer texto del documento (archivo vacío, PDF escaneado "
                "o sin capa de texto)."
            )
            document.save(update_fields=["status", "error_message", "updated_at"])
            return {"document_id": document_id, "chunks": 0, "error": document.error_message}

        chord(embed_chunks_batch.s(ids) for ids in batch_ids)(finalize_ingestion.s(document_id))
        return {"document_id": document_id, "chunks": len(chunks), "batches": len(batch_ids)}
    except Exception as exc:
        if is_transient_error(exc):
            document.status = Document.Status.PENDING
            document.save(update_fields=["status", "updated_at"])
            raise self.retry(exc=exc, countdown=exponential_backoff(self.request.retries))
        document.status = Document.Status.FAILED
        document.error_message = str(exc)[:1000]
        document.save(update_fields=["status", "error_message", "updated_at"])
        raise


def _build_chunker(document: Document) -> HybridChunker:
    from agents.services import get_platform_config

    config = get_platform_config()
    semantic_guard = None
    if config["use_semantic_guard"]:
        service = get_embedding_service()
        semantic_guard = SemanticDriftGuard(embed_fn=service.embed)
    return HybridChunker(
        chunk_size=config["chunk_size"],
        chunk_overlap=config["chunk_overlap"],
        semantic_guard=semantic_guard,
    )


def _batch_size() -> int:
    from agents.services import get_platform_config

    return get_platform_config()["embed_batch_size"]


@shared_task(bind=True, max_retries=3, acks_late=True)
def embed_chunks_batch(self, chunk_ids: List[int]) -> dict:
    chunks = list(Chunk.objects.filter(id__in=chunk_ids))
    if not chunks:
        return {"ok": True, "embedded": 0}

    try:
        service = get_embedding_service()
        db_dim = vector_dim()
        if db_dim and service.embedding_dim and db_dim != service.embedding_dim:
            return {
                "ok": False,
                "chunk_ids": chunk_ids,
                "error": (
                    f"La dimensión del modelo de embeddings ({service.embedding_dim}) no coincide "
                    f"con la columna de vectores ({db_dim}). Ajusta el agente o usa «Reindexar todo» "
                    "tras cambiar la dimensión."
                ),
            }
        vectors = service.embed_texts([chunk.content for chunk in chunks])
        if vectors and db_dim and len(vectors[0]) != db_dim:
            return {
                "ok": False,
                "chunk_ids": chunk_ids,
                "error": (
                    f"Embeddings de {len(vectors[0])} dims, pero la columna espera {db_dim}. "
                    "Cambia la dimensión del agente y reindexa."
                ),
            }
        bm25 = get_bm25_index()
        for chunk, vector in zip(chunks, vectors):
            upsert_embedding(chunk.id, vector, service.model)
            bm25.upsert_chunk(chunk.id, chunk.document_id, chunk.content)
        return {"ok": True, "embedded": len(chunks)}
    except Exception as exc:
        if is_transient_error(exc) and self.request.retries < self.max_retries:
            raise self.retry(exc=exc, countdown=exponential_backoff(self.request.retries))
        if is_transient_error(exc):
            return {"ok": False, "chunk_ids": chunk_ids, "error": f"agotados reintentos: {exc}"}
        return {"ok": False, "chunk_ids": chunk_ids, "error": str(exc)[:500]}


@shared_task(acks_late=True)
def finalize_ingestion(results: List[dict], document_id: int) -> dict:
    document = get_object_or_404(Document, pk=document_id)
    failed = [r for r in results if not r.get("ok", False)]
    if failed:
        document.status = Document.Status.FAILED
        first_error = next((r.get("error", "") for r in failed if r.get("error")), "")
        detail = f" {first_error}" if first_error else ""
        document.error_message = f"{len(failed)} lote(s) fallaron al embeber.{detail}"
    else:
        document.status = Document.Status.READY
    document.save(update_fields=["status", "error_message", "updated_at"])
    return {"document_id": document_id, "status": document.status}
