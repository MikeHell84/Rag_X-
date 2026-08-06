"""Pipeline RAG end-to-end.

Flujo (ver README, sección 2):

1. Búsqueda híbrida: ANN (pgvector) + BM25 (Whoosh) fusionados con RRF.
2. Carga de los chunks candidatos desde Postgres.
3. Re-ranking con el LLM (puntúa relevancia) o cross-encoder.
4. Generación de la respuesta con contexto recortado al presupuesto de tokens.
5. Registro del QueryLog (tokens, latencia, costo estimado).

La generación NUNCA toca el servidor web: se ejecuta en un worker Celery.
"""

import time
from typing import List, Optional

from django.conf import settings
from django.db import transaction

from core.llm import FailoverLLMService, LLMService
from core.rerank import LLMReranker
from core.search import search_from_settings
from core.token_budget import estimate_tokens
from documents.models import Chunk, QueryLog

SYSTEM_PROMPT = (
    "Eres el asistente RAG de una empresa. Responde en español, con precisión y "
    "usando EXCLUSIVAMENTE el contexto proporcionado. Si la respuesta no está en "
    "el contexto, dilo explícitamente ('La información no está disponible en los "
    "documentos indexados'). Cita las fuentes entre corchetes al final de cada "
    "afirmación, por ejemplo [3]. No inventes datos ni mezcles conocimiento general."
)

ANSWER_TEMPLATE = """Contexto (fragmentos del corpus):

{context_blocks}

Pregunta del usuario: {question}
"""


REFORMULATION_PROMPT = (
    "Eres un sistema de preguntas sobre documentos. Reformula la pregunta del usuario "
    "para que sea autónoma (sin depender del historial), conservando el contexto previo. "
    "Responde SOLO con la pregunta reformulada, sin explicaciones."
)


def _reformulate(
    question: str,
    history: List[dict],
    llm: FailoverLLMService,
    model: str,
) -> str:
    if not history:
        return question
    transcript = "\n".join(
        f"{'Usuario' if m.get('role') == 'user' else 'Asistente'}: {m.get('content', '')}"
        for m in history[-6:]
    )
    try:
        response = llm.chat_completion(
            messages=[
                {"role": "system", "content": REFORMULATION_PROMPT},
                {"role": "user", "content": f"Historial:\n{transcript}\n\nÚltima pregunta: {question}"},
            ],
            model=model,
            temperature=0.0,
            max_tokens=256,
        )
        rewritten = (response.get("content") or "").strip()
        return rewritten if rewritten else question
    except Exception:
        return question


def run_rag_pipeline(
    question: str,
    top_k: int | None = None,
    model: str | None = None,
    document_ids: Optional[List[int]] = None,
    history: Optional[List[dict]] = None,
    agent_id: int | None = None,
    on_stage=None,
) -> dict:
    from agents.models import Agent
    from agents.services import (
        get_chat_agent_chain,
        get_platform_config,
        get_reranker_agent_chain,
    )

    def _stage(name: str) -> None:
        if on_stage:
            on_stage(name)

    rag = settings.RAG
    config = get_platform_config()
    chat_chain = get_chat_agent_chain()
    reranker_chain = get_reranker_agent_chain()

    # If a specific agent_id is requested, prioritize it in the chain
    # (it becomes the primary, others become fallback in their original order)
    if agent_id:
        try:
            requested = Agent.objects.get(pk=agent_id, agent_type="chat")
        except Agent.DoesNotExist:
            pass  # fall through to default chain
        else:
            # Reorder: requested agent first, then the rest of the chain minus the requested one
            chat_chain = [requested] + [a for a in chat_chain if a.pk != requested.pk]

    chat_agent = chat_chain[0] if chat_chain else None
    reranker_agent = reranker_chain[0] if reranker_chain else None

    top_k = top_k or (chat_agent.top_k if chat_agent else None) or config["rerank_top_k"]
    model = model or (chat_agent.model if chat_agent else None) or rag["LLM_MODEL"]
    system_prompt = (chat_agent.system_prompt if chat_agent and chat_agent.system_prompt else None) or SYSTEM_PROMPT
    temperature = chat_agent.temperature if chat_agent else 0.2
    max_tokens = chat_agent.max_tokens if chat_agent else 1024
    rerank_model = (reranker_agent.model if reranker_agent else None) or rag["RERANK_MODEL"]

    started = time.perf_counter()

    llm = FailoverLLMService(
        [
            {
                "provider": agent.provider,
                "model": agent.model,
                "api_key": agent.api_key_plain or None,
                "base_url": agent.base_url,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
            }
            for agent in chat_chain
        ]
    ) if chat_chain else LLMService()

    question = _reformulate(question, history or [], llm, model)

    _stage("buscando")
    fused = search_from_settings(question, top_k=config["hybrid_top_k"], document_ids=document_ids)
    chunk_ids = [item["chunk_id"] for item in fused]
    candidates = _load_chunks(chunk_ids)
    candidates = _attach_rrf(candidates, fused)

    _stage("reordenando")

    reranker = LLMReranker(
        model=rerank_model,
        llm=FailoverLLMService(
            [
                {
                    "provider": agent.provider,
                    "model": agent.model,
                    "api_key": agent.api_key_plain,
                    "base_url": agent.base_url,
                    "temperature": agent.temperature,
                    "max_tokens": agent.max_tokens,
                }
                for agent in reranker_chain
            ]
        )
        if reranker_chain
        else None,
    )
    reranked = reranker.rerank(question, candidates, top_n=top_k)

    _stage("generando")

    llm = FailoverLLMService(
        [
            {
                "provider": agent.provider,
                "model": agent.model,
                "api_key": agent.api_key_plain or None,
                "base_url": agent.base_url,
                "temperature": agent.temperature,
                "max_tokens": agent.max_tokens,
            }
            for agent in chat_chain
        ]
    ) if chat_chain else LLMService()
    response = llm.chat_completion(
        messages=_build_messages(question, reranked, model, system_prompt, config["max_context_tokens"]),
        model=model,
        temperature=temperature,
        max_tokens=max_tokens,
    )

    responded_model = response.get("model", model)
    latency_ms = int((time.perf_counter() - started) * 1000)
    cost = LLMService.estimate_cost_usd(
        response["prompt_tokens"], response["completion_tokens"], responded_model
    )

    with transaction.atomic():
        log = QueryLog.objects.create(
            query_text=question,
            embedding_model=rag["EMBEDDING_MODEL"],
            llm_model=responded_model,
            candidate_count=len(candidates),
            rerank_count=len(reranked),
            tokens_prompt=response["prompt_tokens"],
            tokens_completion=response["completion_tokens"],
            total_cost_usd=cost,
            latency_ms=latency_ms,
            answer=response["content"],
            used_agent=chat_agent,
        )

    return {
        "query_id": log.pk,
        "answer": response["content"],
        "sources": [
            {
                "chunk_id": item["id"],
                "document": item["document_title"],
                "section": item["section"],
                "page": item["page"],
                "rrf_score": item.get("rrf_score"),
            }
            for item in reranked
        ],
        "tokens_prompt": response["prompt_tokens"],
        "tokens_completion": response["completion_tokens"],
        "cost_usd": round(cost, 6),
        "latency_ms": latency_ms,
        "model": responded_model,
    }


def _load_chunks(chunk_ids: List[int]) -> List[dict]:
    chunks = Chunk.objects.select_related("document").filter(id__in=chunk_ids)
    by_id = {chunk.id: chunk for chunk in chunks}
    ordered = []
    for cid in chunk_ids:
        chunk = by_id.get(cid)
        if chunk:
            ordered.append(
                {
                    "id": chunk.id,
                    "content": chunk.content,
                    "section": chunk.section,
                    "page": chunk.page,
                    "document_title": chunk.document.title,
                }
            )
    return ordered


def _attach_rrf(candidates: List[dict], fused: List[dict]) -> List[dict]:
    scores = {item["chunk_id"]: item["rrf"] for item in fused}
    for candidate in candidates:
        candidate["rrf_score"] = round(scores.get(candidate["id"], 0.0), 6)
    return candidates


def _build_messages(
    question: str,
    contexts: List[dict],
    model: str,
    system_prompt: str = SYSTEM_PROMPT,
    max_context_tokens: int = 32000,
) -> List[dict]:
    context_blocks = "\n\n".join(
        f"[{i}] (Fuente: {c['document_title']}, sección: {c['section']})\n{c['content']}"
        for i, c in enumerate(contexts, start=1)
    )
    user_prompt = ANSWER_TEMPLATE.format(context_blocks=context_blocks, question=question)

    budget = max_context_tokens - estimate_tokens(system_prompt) - 512
    while estimate_tokens(user_prompt) > budget and contexts:
        contexts = contexts[:-1]
        context_blocks = "\n\n".join(
            f"[{i}] (Fuente: {c['document_title']}, sección: {c['section']})\n{c['content']}"
            for i, c in enumerate(contexts, start=1)
        )
        user_prompt = ANSWER_TEMPLATE.format(context_blocks=context_blocks, question=question)

    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]
