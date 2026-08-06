from celery.result import AsyncResult
from django.conf import settings
from django.http import StreamingHttpResponse
from rest_framework import status
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from django.views import View

from documents.models import Document, QueryLog, Tenant
from documents.serializers import QueryLogSerializer


def _get_tenant(request) -> Tenant | None:
    tid = request.headers.get("X-Tenant-Id") or request.query_params.get("tenant")
    if not tid:
        return None
    try:
        return Tenant.objects.get(pk=int(tid)) if tid.isdigit() else Tenant.objects.get(slug=tid)
    except (Tenant.DoesNotExist, ValueError):
        return None


def _tenant_document_ids(request) -> list[int] | None:
    tenant = _get_tenant(request)
    if not tenant:
        return None
    return list(Document.objects.filter(tenant=tenant).values_list("id", flat=True))


class QueryView(APIView):
    throttle_scope = "query"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        question = (request.data.get("question") or "").strip()
        if not question:
            return Response({"error": "Campo 'question' requerido"}, status=status.HTTP_400_BAD_REQUEST)
        if len(question) > 2000:
            return Response({"error": "Pregunta demasiado larga"}, status=status.HTTP_400_BAD_REQUEST)

        from .tasks import generate_answer

        document_ids = request.data.get("document_ids")
        tenant_doc_ids = _tenant_document_ids(request)
        if tenant_doc_ids is not None:
            if document_ids:
                document_ids = [did for did in document_ids if did in tenant_doc_ids]
            else:
                document_ids = tenant_doc_ids
        topic = (request.data.get("topic") or "").strip()
        if topic and document_ids:
            topic_ids = set(
                Document.objects.filter(topic=topic).values_list("id", flat=True)
            )
            document_ids = [did for did in document_ids if did in topic_ids]
        history = request.data.get("history")
        if document_ids and not isinstance(document_ids, list):
            document_ids = None
        if history and not isinstance(history, list):
            history = None

        task = generate_answer.delay(
            question,
            top_k=request.data.get("top_k"),
            model=request.data.get("model"),
            document_ids=document_ids,
            history=history,
            agent_id=request.data.get("agent_id"),
        )
        return Response(
            {"task_id": task.id, "status": "processing", "queued": True},
            status=status.HTTP_202_ACCEPTED,
        )


class QueryResultView(APIView):
    def get(self, request, task_id):
        result = AsyncResult(task_id)
        payload = {"task_id": task_id}
        if not result.ready():
            payload["status"] = "processing"
        elif result.failed():
            payload["status"] = "error"
            payload["error"] = str(result.info)[:1000] if result.info else "Tarea fallida"
        else:
            payload["status"] = "done"
            payload["result"] = result.result
        return Response(payload)


class QueryLogFeedbackView(APIView):
    def post(self, request, log_id):
        feedback = (request.data.get("feedback") or "").strip()
        if feedback not in QueryLog.Feedback.values:
            return Response(
                {"error": "feedback debe ser 'up' o 'down'"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            log = QueryLog.objects.get(pk=log_id)
        except QueryLog.DoesNotExist:
            return Response({"error": "Registro no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        log.feedback = feedback
        log.save(update_fields=["feedback", "updated_at"])
        return Response({"id": log.pk, "feedback": feedback})


class QueryLogListView(APIView):
    def get(self, request):
        tenant = _get_tenant(request)
        logs = QueryLog.objects.all()
        if tenant:
            # filtrar por documentos del tenant a través de la respuesta (no hay FK directo)
            # aproximación: filtrar logs cuyos chunks pertenezcan a docs del tenant
            pass
        logs = logs[:200]
        return Response({"results": QueryLogSerializer(logs, many=True).data})


class QueryStreamView(View):
    """SSE: transmite las etapas y el resultado final de una consulta en vivo."""

    def get(self, request, task_id):
        import json

        import redis as redis_py

        result = AsyncResult(task_id)

        def _sse(event, data):
            return f"event: {event}\ndata: {json.dumps(data)}\n\n"

        def stream():
            client = redis_py.from_url(settings.CELERY_BROKER_URL)
            pubsub = client.pubsub(ignore_subscribe_messages=True)
            pubsub.subscribe(f"rag:query:{task_id}")
            try:
                yield _sse("connected", {"task_id": task_id})
                if result.ready():
                    if result.failed():
                        yield _sse("error", {"error": str(result.info)[:1000]})
                    else:
                        yield _sse("done", result.result)
                    return
                for message in pubsub.listen():
                    if message.get("type") != "message":
                        continue
                    try:
                        payload = json.loads(message["data"])
                    except (TypeError, ValueError):
                        continue
                    yield _sse(payload["event"], payload.get("data", {}))
                    if payload["event"] in ("done", "error"):
                        break
            finally:
                try:
                    pubsub.close()
                    client.close()
                except Exception:
                    pass

        response = StreamingHttpResponse(stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"
        return response
