from django.db import models


class Tenant(models.Model):
    name = models.CharField(max_length=100)
    slug = models.SlugField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Topic(models.Model):
    """Catálogo de temas independiente de los documentos.

    Cada tema agrupa su propia documentación (Document.topic == Topic.name)
    y sus propias conversaciones (Conversation.topic == Topic.name), de modo
    que consultar en un tema nunca usa documentos de otros temas.
    """

    name = models.CharField(max_length=100, unique=True)
    description = models.CharField(max_length=300, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self) -> str:
        return self.name


class Document(models.Model):
    class Status(models.TextChoices):
        PENDING = "pending", "Pendiente"
        PROCESSING = "processing", "Procesando"
        CHUNKED = "chunked", "Fragmentado"
        EMBEDDED = "embedded", "Embeddings listos"
        READY = "ready", "Listo"
        FAILED = "failed", "Fallido"

    title = models.CharField(max_length=500)
    file = models.FileField(upload_to="ingest/%Y/%m/")
    source_type = models.CharField(
        max_length=10,
        choices=(("pdf", "PDF"), ("docx", "DOCX"), ("md", "Markdown"), ("txt", "Texto")),
    )
    content_hash = models.CharField(max_length=64, unique=True)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    total_chunks = models.PositiveIntegerField(default=0)
    total_tokens = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    metadata = models.JSONField(default=dict, blank=True)
    tenant = models.ForeignKey(Tenant, on_delete=models.CASCADE, related_name="documents", null=True, blank=True)
    topic = models.CharField(max_length=100, blank=True, help_text="Tema o categor�a del documento")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return self.title


class Chunk(models.Model):
    document = models.ForeignKey(Document, on_delete=models.CASCADE, related_name="chunks")
    index = models.PositiveIntegerField()
    section = models.CharField(max_length=500, blank=True)
    page = models.PositiveIntegerField(null=True, blank=True)
    content = models.TextField()
    token_count = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["document", "index"]
        constraints = [
            models.UniqueConstraint(fields=["document", "index"], name="unique_chunk_index")
        ]

    def __str__(self) -> str:
        return f"{self.document_id}#{self.index}"


class QueryLog(models.Model):
    class Feedback(models.TextChoices):
        UP = "up", "Útil"
        DOWN = "down", "No útil"

    query_text = models.TextField()
    embedding_model = models.CharField(max_length=128, blank=True)
    llm_model = models.CharField(max_length=128, blank=True)
    candidate_count = models.PositiveIntegerField(default=0)
    rerank_count = models.PositiveIntegerField(default=0)
    tokens_prompt = models.PositiveIntegerField(default=0)
    tokens_completion = models.PositiveIntegerField(default=0)
    total_cost_usd = models.DecimalField(max_digits=10, decimal_places=6, default=0)
    latency_ms = models.PositiveIntegerField(default=0)
    answer = models.TextField(blank=True)
    feedback = models.CharField(max_length=10, choices=Feedback.choices, blank=True, default="")
    used_agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="query_logs",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.query_text[:60]

    class Meta:
        ordering = ["-created_at"]


class Conversation(models.Model):
    """Historial de conversación guardado por tema/agente.

    Permite al RAG recordar contexto previo cuando el usuario cambia de agente
    o continúa una conversación sobre el mismo tema.
    """

    class Visibility(models.TextChoices):
        PRIVATE = "private", "Privada"
        SHARED = "shared", "Compartida"

    title = models.CharField(max_length=200, blank=True)
    topic = models.CharField(max_length=100, blank=True, help_text="Tema o categoría de la conversación")
    agent = models.ForeignKey(
        "agents.Agent",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="conversations",
    )
    visibility = models.CharField(max_length=10, choices=Visibility.choices, default=Visibility.PRIVATE)
    session_key = models.CharField(max_length=100, blank=True, help_text="Identificador de sesión del usuario")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return self.title or f"Conversación {self.id}"


class ConversationMessage(models.Model):
    """Mensaje individual dentro de una conversación guardada."""

    class Role(models.TextChoices):
        USER = "user", "Usuario"
        ASSISTANT = "assistant", "Asistente"
        SYSTEM = "system", "Sistema"

    conversation = models.ForeignKey(
        Conversation,
        on_delete=models.CASCADE,
        related_name="messages",
    )
    role = models.CharField(max_length=10, choices=Role.choices)
    content = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self) -> str:
        return f"{self.role}: {self.content[:60]}"
