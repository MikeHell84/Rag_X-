import hashlib
from pathlib import Path

from django.conf import settings
from django.db import connection, transaction
from rest_framework import status
from rest_framework.parsers import MultiPartParser
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from core.bm25 import get_bm25_index
from core.url_ingest import UrlFetchError, fetch_markdown

from .models import Document, Tenant, Conversation, ConversationMessage, Chunk, QueryLog, Topic
from .serializers import DocumentSerializer, ConversationSerializer, DocumentCreateSerializer
from .tasks import ingest_document

EXT_MAP = {"pdf": "pdf", "docx": "docx", "md": "md", "txt": "txt"}


def _get_tenant(request) -> Tenant | None:
    """Obtiene tenant desde header X-Tenant-Id o slug."""
    tid = request.headers.get("X-Tenant-Id") or request.query_params.get("tenant")
    if not tid:
        return None
    try:
        return Tenant.objects.get(pk=int(tid)) if tid.isdigit() else Tenant.objects.get(slug=tid)
    except (Tenant.DoesNotExist, ValueError):
        return None


def _tenant_queryset(request):
    tenant = _get_tenant(request)
    qs = Document.objects.all()
    if tenant:
        qs = qs.filter(tenant=tenant)
    return qs


class DocumentUploadView(APIView):
    parser_classes = [MultiPartParser]
    throttle_scope = "upload"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        file = request.FILES.get("file")
        if file is None:
            return Response({"error": "Campo 'file' requerido"}, status=status.HTTP_400_BAD_REQUEST)

        ext = Path(file.name).suffix.lower().lstrip(".")
        if ext not in EXT_MAP:
            return Response(
                {"error": f"Extensión .{ext} no soportada. Use pdf, docx, md o txt."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        max_bytes = settings.RAG["MAX_UPLOAD_MB"] * 1024 * 1024
        if file.size > max_bytes:
            return Response(
                {"error": f"Archivo supera el límite de {settings.RAG['MAX_UPLOAD_MB']} MB"},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )

        content = file.read()
        content_hash = hashlib.sha256(content).hexdigest()
        existing = Document.objects.filter(content_hash=content_hash).first()
        if existing:
            tenant = _get_tenant(request)
            if tenant and existing.tenant and existing.tenant != tenant:
                pass  # cross-tenant conflict: tratar como nuevo
            else:
                return Response(
                    {"id": existing.id, "duplicate": True, "message": "Documento ya indexado"},
                    status=status.HTTP_409_CONFLICT,
                )

        file.seek(0)
        tenant = _get_tenant(request)
        topic = (request.data.get("topic") or "").strip()
        if topic:
            Topic.objects.get_or_create(name=topic)
        document = Document.objects.create(
            title=file.name,
            file=file,
            source_type=EXT_MAP[ext],
            content_hash=content_hash,
            status=Document.Status.PENDING,
            tenant=tenant,
            topic=topic,
        )
        task = ingest_document.delay(document.id)
        document.metadata["task_id"] = task.id
        document.save(update_fields=["metadata", "updated_at"])

        return Response(
            {"id": document.id, "task_id": task.id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentFromUrlView(APIView):
    """Ingesta desde una URL: baja la página, la convierte a Markdown y la indexa.

    Body JSON: {"url": "...", "topic": "opcional"}
    """

    throttle_scope = "upload"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request):
        url = (request.data.get("url") or "").strip()
        if not url:
            return Response({"error": "Campo 'url' requerido"}, status=status.HTTP_400_BAD_REQUEST)
        if not (url.startswith("http://") or url.startswith("https://")):
            return Response(
                {"error": "La URL debe comenzar con http:// o https://"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        topic = (request.data.get("topic") or "").strip()
        tenant = _get_tenant(request)

        from django.conf import settings

        try:
            path, markdown, title = fetch_markdown(url, settings.MEDIA_ROOT)
        except UrlFetchError as exc:
            return Response({"error": str(exc)}, status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        content_hash = hashlib.sha256(url.encode("utf-8")).hexdigest()
        existing = Document.objects.filter(content_hash=content_hash).first()
        if existing:
            return Response(
                {"id": existing.id, "duplicate": True, "message": "URL ya indexada"},
                status=status.HTTP_409_CONFLICT,
            )

        from django.core.files import File as DjangoFile

        if topic:
            Topic.objects.get_or_create(name=topic)

        with path.open("rb") as fh:
            document = Document.objects.create(
                title=title,
                file=DjangoFile(fh, name=path.name),
                source_type="md",
                content_hash=content_hash,
                status=Document.Status.PENDING,
                tenant=tenant,
                topic=topic,
                metadata={"url": url},
            )
        task = ingest_document.delay(document.id)
        document.metadata["task_id"] = task.id
        document.save(update_fields=["metadata", "updated_at"])

        return Response(
            {
                "id": document.id,
                "task_id": task.id,
                "status": "accepted",
                "title": title,
                "markdown_file": path.name,
            },
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentDetailView(APIView):
    def get(self, request, document_id):
        try:
            document = _tenant_queryset(request).get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"error": "Documento no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        return Response(DocumentSerializer(document).data)

    def delete(self, request, document_id):
        try:
            document = _tenant_queryset(request).get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"error": "Documento no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            get_bm25_index().delete_document(document_id)
            title = document.title
            try:
                document.file.delete(save=False)
            except Exception:
                pass
            document.delete()

        return Response({"deleted": True, "title": title})

    def patch(self, request, document_id):
        try:
            document = _tenant_queryset(request).get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"error": "Documento no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        allowed_fields = {"title", "topic", "url"}
        update_fields = []

        if "title" in request.data:
            document.title = request.data["title"]
            update_fields.append("title")

        if "topic" in request.data:
            document.topic = request.data["topic"]
            update_fields.append("topic")

        if "url" in request.data:
            if not document.metadata:
                document.metadata = {}
            document.metadata["url"] = request.data["url"]
            update_fields.append("metadata")

        if update_fields:
            update_fields.append("updated_at")
            document.save(update_fields=update_fields)

        return Response(DocumentSerializer(document).data)


class DocumentRetryView(APIView):
    throttle_scope = "upload"
    throttle_classes = [ScopedRateThrottle]

    def post(self, request, document_id):
        try:
            document = _tenant_queryset(request).get(pk=document_id)
        except Document.DoesNotExist:
            return Response({"error": "Documento no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        document.status = Document.Status.PENDING
        document.error_message = ""
        document.save(update_fields=["status", "error_message", "updated_at"])

        task = ingest_document.delay(document.id)
        document.metadata["task_id"] = task.id
        document.save(update_fields=["metadata", "updated_at"])

        return Response(
            {"id": document.id, "task_id": task.id, "status": "accepted"},
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentReindexView(APIView):
    """Re-encola la ingesta de todos los documentos (borra chunks/embeddings previos)."""

    def post(self, request):
        documents = _tenant_queryset(request)
        task_ids = []
        for document in documents:
            document.status = Document.Status.PENDING
            document.error_message = ""
            document.save(update_fields=["status", "error_message", "updated_at"])
            task = ingest_document.delay(document.id)
            document.metadata["task_id"] = task.id
            document.save(update_fields=["metadata", "updated_at"])
            task_ids.append(task.id)
        return Response(
            {"queued": len(task_ids), "task_ids": task_ids},
            status=status.HTTP_202_ACCEPTED,
        )


class DocumentListView(APIView):
    def get(self, request):
        documents = _tenant_queryset(request)
        topic = request.query_params.get("topic")
        if topic:
            documents = documents.filter(topic=topic)
        page = self.request.query_params.get("page", 1)
        page_size = int(self.request.query_params.get("page_size", 50))
        start = (int(page) - 1) * page_size
        queryset = documents[start : start + page_size]
        return Response(
            {
                "count": documents.count(),
                "results": DocumentSerializer(queryset, many=True).data,
            }
        )


class ConversationView(APIView):
    """CRUD de conversaciones guardadas.

    - GET ?topic=X&agent_id=Y → devuelve conversaciones filtradas
    - POST → crea nueva conversación
    - GET /conversations/<id>/ → detalle con mensajes
    - POST /conversations/<id>/messages/ → agrega mensaje
    """

    def get(self, request, conversation_id=None):
        if conversation_id:
            try:
                conv = Conversation.objects.get(pk=conversation_id)
            except Conversation.DoesNotExist:
                return Response({"error": "Conversación no encontrada"}, status=status.HTTP_404_NOT_FOUND)
            return Response(ConversationSerializer(conv).data)

        conversations = Conversation.objects.all()
        topic = request.query_params.get("topic")
        if topic:
            conversations = conversations.filter(topic=topic)
        agent_id = request.query_params.get("agent_id")
        if agent_id:
            conversations = conversations.filter(agent_id=agent_id)
        session = request.query_params.get("session")
        if session:
            conversations = conversations.filter(session_key=session)
        return Response(
            {
                "count": conversations.count(),
                "results": ConversationSerializer(conversations.order_by("-updated_at")[:50], many=True).data,
            }
        )

    def post(self, request, conversation_id=None):
        if conversation_id:
            return Response({"error": "Método no permitido en detalle"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)

        serializer = ConversationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data, status=status.HTTP_201_CREATED)

    def patch(self, request, conversation_id=None):
        if not conversation_id:
            return Response({"error": "ID de conversación requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            conv = Conversation.objects.get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversación no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        serializer = ConversationSerializer(conv, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)

    def delete(self, request, conversation_id=None):
        if not conversation_id:
            return Response({"error": "ID de conversación requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            Conversation.objects.get(pk=conversation_id).delete()
        except Conversation.DoesNotExist:
            return Response({"error": "Conversación no encontrada"}, status=status.HTTP_404_NOT_FOUND)
        return Response({"deleted": True})


class ConversationMessageView(APIView):
    """Agrega mensajes a una conversación existente."""

    def post(self, request, conversation_id):
        try:
            conv = Conversation.objects.get(pk=conversation_id)
        except Conversation.DoesNotExist:
            return Response({"error": "Conversación no encontrada"}, status=status.HTTP_404_NOT_FOUND)

        role = (request.data.get("role") or "").strip()
        content = (request.data.get("content") or "").strip()
        if role not in ConversationMessage.Role.values:
            return Response({"error": "Rol inválido (user/assistant/system)"}, status=status.HTTP_400_BAD_REQUEST)
        if not content:
            return Response({"error": "Contenido requerido"}, status=status.HTTP_400_BAD_REQUEST)

        msg = ConversationMessage.objects.create(conversation=conv, role=role, content=content)
        conv.save(update_fields=["updated_at"])
        return Response({"id": msg.id, "role": msg.role, "content": msg.content, "created_at": msg.created_at}, status=status.HTTP_201_CREATED)


class DataCleanupView(APIView):
    """Elimina todos los documentos, chunks, embeddings, conversaciones y logs de query.

    Útil para limpiar datos de prueba. Requiere confirmación explícita.
    """

    def delete(self, request):
        confirm = request.data.get("confirm") or request.query_params.get("confirm")
        if confirm != "yes":
            return Response(
                {"error": "Debes enviar confirm=yes para proceder con la limpieza total."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        with transaction.atomic():
            ConversationMessage.objects.all().delete()
            Conversation.objects.all().delete()
            QueryLog.objects.all().delete()
            get_bm25_index().delete_all_documents()
            Chunk.objects.all().delete()
            Document.objects.all().delete()
            from core.vector_store import count_embeddings
            with connection.cursor() as cursor:
                cursor.execute("DELETE FROM chunk_embeddings")
                cursor.execute("DROP INDEX IF EXISTS chunk_embeddings_hnsw_idx")
                cursor.execute("CREATE INDEX chunk_embeddings_hnsw_idx ON chunk_embeddings USING hnsw (embedding vector_cosine_ops)")
        return Response({"deleted": True, "message": "Todos los datos han sido eliminados."})


class TopicListView(APIView):
    """CRUD de temas (catálogo independiente de los documentos).

    - GET → lista todos los temas del catálogo con número de documentos
    - POST {name, description?} → crea un tema nuevo
    - PATCH /topics/<id>/ {name?, description?} → renombra/actualiza (y propaga a docs/conversaciones)
    - DELETE /topics/<id>/ → elimina el tema (los docs/conversaciones quedan sin tema)
    """

    def _topic_data(self, topic):
        doc_count = Document.objects.filter(topic=topic.name).count()
        conv_count = Conversation.objects.filter(topic=topic.name).count()
        return {
            "id": topic.id,
            "name": topic.name,
            "description": topic.description,
            "document_count": doc_count,
            "conversation_count": conv_count,
            "created_at": topic.created_at,
        }

    def get(self, request, topic_id=None):
        if topic_id:
            try:
                topic = Topic.objects.get(pk=topic_id)
            except Topic.DoesNotExist:
                return Response({"error": "Tema no encontrado"}, status=status.HTTP_404_NOT_FOUND)
            return Response(self._topic_data(topic))

        legacy_names = list(
            Document.objects.exclude(topic__exact="").values_list("topic", flat=True).distinct()
        )
        known = {t.name for t in Topic.objects.all()}
        for name in legacy_names:
            if name not in known:
                Topic.objects.get_or_create(name=name)

        topics = list(Topic.objects.all())
        data = [self._topic_data(t) for t in topics]
        data.sort(key=lambda x: x["name"].lower())
        return Response({"topics": data})

    def post(self, request, topic_id=None):
        if topic_id:
            return Response({"error": "Método no permitido en detalle"}, status=status.HTTP_405_METHOD_NOT_ALLOWED)
        name = (request.data.get("name") or "").strip()
        if not name:
            return Response({"error": "Campo 'name' requerido"}, status=status.HTTP_400_BAD_REQUEST)
        if Topic.objects.filter(name=name).exists():
            return Response({"error": "Ya existe un tema con ese nombre"}, status=status.HTTP_409_CONFLICT)
        topic = Topic.objects.create(name=name, description=(request.data.get("description") or "").strip())
        return Response(self._topic_data(topic), status=status.HTTP_201_CREATED)

    def patch(self, request, topic_id=None):
        if not topic_id:
            return Response({"error": "ID de tema requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            topic = Topic.objects.get(pk=topic_id)
        except Topic.DoesNotExist:
            return Response({"error": "Tema no encontrado"}, status=status.HTTP_404_NOT_FOUND)

        old_name = topic.name
        new_name = (request.data.get("name") or "").strip()
        if new_name and new_name != old_name:
            if Topic.objects.filter(name=new_name).exclude(pk=topic.id).exists():
                return Response({"error": "Ya existe un tema con ese nombre"}, status=status.HTTP_409_CONFLICT)
            with transaction.atomic():
                Document.objects.filter(topic=old_name).update(topic=new_name)
                Conversation.objects.filter(topic=old_name).update(topic=new_name)
                topic.name = new_name
        if "description" in request.data:
            topic.description = (request.data.get("description") or "").strip()
        topic.save()
        return Response(self._topic_data(topic))

    def delete(self, request, topic_id=None):
        if not topic_id:
            return Response({"error": "ID de tema requerido"}, status=status.HTTP_400_BAD_REQUEST)
        try:
            topic = Topic.objects.get(pk=topic_id)
        except Topic.DoesNotExist:
            return Response({"error": "Tema no encontrado"}, status=status.HTTP_404_NOT_FOUND)
        with transaction.atomic():
            Document.objects.filter(topic=topic.name).update(topic="")
            Conversation.objects.filter(topic=topic.name).update(topic="")
            topic.delete()
        return Response({"deleted": True})
