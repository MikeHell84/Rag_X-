import json

from django.http import HttpResponse
from django.views import View
from django.views.generic import TemplateView

from documents.models import QueryLog
from core.vector_store import count_embeddings


class IndexView(TemplateView):
    template_name = "api/index.html"


class HealthView(View):
    def get(self, request):
        from django.db import connection
        from django.core.cache import cache

        db_ok = False
        redis_ok = False
        try:
            connection.ensure_connection()
            db_ok = True
        except Exception:
            pass
        try:
            cache.set("health_check", "ok", 1)
            redis_ok = cache.get("health_check") == "ok"
        except Exception:
            pass
        return HttpResponse(
            json.dumps(
                {
                    "status": "ok" if db_ok and redis_ok else "degraded",
                    "database": "ok" if db_ok else "error",
                    "redis": "ok" if redis_ok else "error",
                    "vector_embeddings": count_embeddings(),
                }
            ),
            content_type="application/json",
        )


class MetricsView(View):
    """Expone métricas en formato Prometheus text."""

    def get(self, request):
        import json

        lines = []

        # Documentos
        from documents.models import Document
        docs_total = Document.objects.count()
        docs_by_status = {}
        for status, _ in Document.Status.choices:
            docs_by_status[status] = Document.objects.filter(status=status).count()
        lines.append(f'rag_documents_total {docs_total}')
        for status, count in docs_by_status.items():
            lines.append(f'rag_documents_status{{status="{status}"}} {count}')

        # Chunks y embeddings
        from documents.models import Chunk
        chunks_total = Chunk.objects.count()
        emb_total = count_embeddings()
        lines.append(f'rag_chunks_total {chunks_total}')
        lines.append(f'rag_embeddings_total {emb_total}')

        # Consultas
        logs = QueryLog.objects.all()
        queries_total = logs.count()
        queries_degraded = logs.filter(answer__icontains="degradado").count()
        lines.append(f'rag_queries_total {queries_total}')
        lines.append(f'rag_queries_degraded {queries_degraded}')

        # Costos y latencia (últimas 100)
        recent = logs.order_by("-created_at")[:100]
        if recent:
            total_cost = sum(float(log.total_cost_usd) for log in recent)
            avg_latency = sum(log.latency_ms for log in recent) / len(recent)
            lines.append(f'rag_cost_usd_recent_total {total_cost:.6f}')
            lines.append(f'rag_latency_ms_avg_recent {avg_latency:.1f}')

        # Feedback
        feedback_up = logs.filter(feedback="up").count()
        feedback_down = logs.filter(feedback="down").count()
        lines.append(f'rag_feedback_up {feedback_up}')
        lines.append(f'rag_feedback_down {feedback_down}')

        return HttpResponse("\n".join(lines) + "\n", content_type="text/plain; version=0.0.4")