"""Búsqueda híbrida: fusión por Reciprocal Rank Fusion (RRF).

1. vector_search()  -> ANN por similitud coseno en pgvector (HNSW).
2. bm25_search()    -> coincidencia léxica en el índice Whoosh.
3. rrf_fusion()     -> combina los dos rankings sin depender de escalas.
4. mmr_select()     -> diversidad: evita fragmentos casi idénticos.
5. hybrid_search()  -> pipeline completo con filtros por documento, recency
                       boost y parámetros de tuning configurables.
"""

from typing import List, Optional

from django.conf import settings

from . import vector_store
from .bm25 import get_bm25_index
from .embeddings import get_embedding_service

RRF_K = 60


def rrf_fusion(
    vector_hits: List[dict], bm25_hits: List[dict], k: Optional[int] = None
) -> List[dict]:
    k = k or RRF_K
    scores: dict = {}
    for rank, hit in enumerate(vector_hits, start=1):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    for rank, hit in enumerate(bm25_hits, start=1):
        cid = hit["chunk_id"]
        scores[cid] = scores.get(cid, 0.0) + 1.0 / (k + rank)
    ranked = sorted(scores.items(), key=lambda item: item[1], reverse=True)
    return [{"chunk_id": cid, "rrf": score} for cid, score in ranked]


def _cosine(a: List[float], b: List[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sum(x * x for x in a) ** 0.5
    nb = sum(y * y for y in b) ** 0.5
    if not na or not nb:
        return 0.0
    return dot / (na * nb)


def mmr_select(
    ranked: List[dict],
    embeddings: dict,
    lambda_: float = 0.7,
    top_k: Optional[int] = None,
) -> List[dict]:
    """Maximum Marginal Relevance: combina relevancia (RRF) con diversidad.

    Penaliza seleccionar un fragmento demasiado similar (coseno) a los ya
    elegidos. lambda_ alto = más relevancia; bajo = más diversidad.
    """
    top_k = top_k or len(ranked)
    if not ranked:
        return []
    remaining = list(ranked)
    selected: List[dict] = []
    while remaining and len(selected) < top_k:
        best_index, best_score = -1, float("-inf")
        for i, item in enumerate(remaining):
            relevance = item["rrf"]
            if selected:
                penalty = max(
                    _cosine(embeddings.get(item["chunk_id"], []), embeddings.get(s["chunk_id"], []))
                    for s in selected
                )
            else:
                penalty = 0.0
            score = lambda_ * relevance - (1 - lambda_) * penalty
            if score > best_score:
                best_score, best_index = score, i
        if best_index < 0:
            break
        selected.append(remaining.pop(best_index))
    return selected


def _recency_map(chunk_ids: List[int]) -> dict:
    """{chunk_id: días de antigüedad} según updated_at del documento."""
    if not chunk_ids:
        return {}
    from django.db import connection

    with connection.cursor() as cursor:
        cursor.execute(
            """
            SELECT c.id, EXTRACT(EPOCH FROM (NOW() - d.updated_at)) / 86400.0
            FROM documents_chunk c
            JOIN documents_document d ON d.id = c.document_id
            WHERE c.id = ANY(%s)
            """,
            [chunk_ids],
        )
        return {row[0]: float(row[1]) for row in cursor.fetchall()}


def _apply_recency(
    fused: List[dict],
    window_days: int,
    boost: float,
) -> List[dict]:
    if not fused or window_days <= 0 or boost <= 0:
        return fused
    age = _recency_map([item["chunk_id"] for item in fused])
    for item in fused:
        days = age.get(item["chunk_id"], window_days + 1)
        if days <= window_days:
            item["rrf"] = item["rrf"] + boost / (1.0 + days)
    return sorted(fused, key=lambda item: item["rrf"], reverse=True)


def hybrid_search(
    query_text: str,
    top_k: int = 20,
    candidate_multiplier: int = 2,
    document_ids: Optional[List[int]] = None,
    rrf_k: Optional[int] = None,
    ef_search: Optional[int] = None,
    mmr_lambda: Optional[float] = None,
    recency_days: Optional[int] = None,
    recency_boost: Optional[float] = None,
) -> List[dict]:
    embedding_service = get_embedding_service()
    query_embedding = embedding_service.embed(query_text)

    vector_hits = vector_store.vector_search(
        query_embedding,
        top_k=top_k * candidate_multiplier,
        ef_search=ef_search,
        document_ids=document_ids,
    )
    bm25_hits = get_bm25_index().search(
        query_text, limit=top_k * candidate_multiplier, document_ids=document_ids
    )

    fused = rrf_fusion(vector_hits, bm25_hits, k=rrf_k)
    fused = _apply_recency(fused, recency_days or 0, recency_boost or 0.0)

    if mmr_lambda is not None and fused:
        embeddings = vector_store.get_embeddings([item["chunk_id"] for item in fused])
        fused = mmr_select(fused, embeddings, lambda_=mmr_lambda, top_k=top_k)
    return fused[:top_k]


def search_from_settings(
    query_text: str,
    top_k: int | None = None,
    document_ids: Optional[List[int]] = None,
) -> List[dict]:
    rag = settings.RAG
    return hybrid_search(
        query_text,
        top_k=top_k or rag["HYBRID_TOP_K"],
        candidate_multiplier=2,
        document_ids=document_ids,
        rrf_k=rag.get("RRF_K"),
        ef_search=rag.get("VECTOR_EF_SEARCH"),
        mmr_lambda=rag.get("MMR_LAMBDA"),
        recency_days=rag.get("RECENCY_WINDOW_DAYS"),
        recency_boost=rag.get("RECENCY_BOOST"),
    )
