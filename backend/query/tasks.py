"""Tareas asíncronas de consulta.

generate_answer es la pieza que garantiza que el servidor web nunca se
bloquea: el endpoint encola la tarea y responde 202; el worker ejecuta la
búsqueda híbrida + re-ranking + generación. Retries con exponential backoff
sobre rate limits y degradación elegante ante fallo definitivo.
"""

import json
import random
from datetime import timedelta
from typing import List, Optional

import redis as redis_py
from celery import shared_task
from django.conf import settings
from django.utils import timezone

from core.providers import is_transient_error

from .service import run_rag_pipeline


def exponential_backoff(retries: int, base: float = 2.0, cap: float = 120.0) -> float:
    return min(base ** (retries + 1), cap) + random.uniform(0, 0.5)


def publish_stage(task_id: str, event: str, data: dict) -> None:
    try:
        client = redis_py.from_url(settings.CELERY_BROKER_URL)
        client.publish(f"rag:query:{task_id}", json.dumps({"event": event, "data": data}))
        client.close()
    except Exception:
        pass


@shared_task(bind=True, max_retries=3, acks_late=True)
def generate_answer(
    self,
    question: str,
    top_k: int | None = None,
    model: str | None = None,
    document_ids: Optional[List[int]] = None,
    history: Optional[List[dict]] = None,
    agent_id: int | None = None,
) -> dict:
    task_id = self.request.id
    publish_stage(task_id, "stage", {"stage": "iniciando"})

    def on_stage(stage: str) -> None:
        publish_stage(task_id, "stage", {"stage": stage})

    try:
        result = run_rag_pipeline(
            question,
            top_k=top_k,
            model=model,
            document_ids=document_ids,
            history=history,
            agent_id=agent_id,
            on_stage=on_stage,
        )
        publish_stage(task_id, "done", result)
        return result
    except Exception as exc:
        if is_transient_error(exc):
            if self.request.retries >= self.max_retries:
                result = _degraded_response(question, exc)
                publish_stage(task_id, "error", {"error": str(exc)[:500]})
                return result
            raise self.retry(exc=exc, countdown=exponential_backoff(self.request.retries))
        result = _degraded_response(question, exc)
        publish_stage(task_id, "error", {"error": str(exc)[:500]})
        return result


def _degraded_response(question: str, exc: Exception) -> dict:
    return {
        "answer": (
            "No pude generar una respuesta completa porque el proveedor de IA "
            f"reportó un problema (fallo definitivo tras reintentos: {exc}). "
            "El sistema está degradado; inténtelo en unos minutos."
        ),
        "sources": [],
        "tokens_prompt": 0,
        "tokens_completion": 0,
        "cost_usd": 0.0,
        "latency_ms": 0,
        "model": "degraded",
        "degraded": True,
    }


@shared_task()
def purge_old_query_logs(keep_days: int = 30) -> dict:
    from documents.models import QueryLog

    cutoff = timezone.now() - timedelta(days=keep_days)
    deleted, _ = QueryLog.objects.filter(created_at__lt=cutoff).delete()
    return {"deleted": deleted}
