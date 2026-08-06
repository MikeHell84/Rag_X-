from django.db import models

from .crypto import decrypt_secret


class AgentType(models.TextChoices):
    CHAT = "chat", "Generación (LLM)"
    EMBEDDING = "embedding", "Embeddings"
    RERANKER = "reranker", "Re-ranking"


class AgentProvider(models.TextChoices):
    OPENAI = "openai", "OpenAI"
    ANTHROPIC = "anthropic", "Anthropic (Claude)"
    GOOGLE = "google", "Google (Gemini)"
    MISTRAL = "mistral", "Mistral"
    GROQ = "groq", "Groq"
    OLLAMA = "ollama", "Ollama (local)"
    OPENROUTER = "openrouter", "OpenRouter"
    CUSTOM = "custom", "OpenAI-compatible (base_url)"


class Agent(models.Model):
    name = models.CharField(max_length=100, unique=True)
    agent_type = models.CharField(max_length=20, choices=AgentType.choices)
    provider = models.CharField(max_length=20, choices=AgentProvider.choices, default=AgentProvider.OPENAI)
    model = models.CharField(max_length=128)
    base_url = models.CharField(max_length=255, blank=True)
    description = models.TextField(blank=True)

    temperature = models.FloatField(default=0.2)
    max_tokens = models.PositiveIntegerField(default=1024)
    top_k = models.PositiveIntegerField(default=5)
    system_prompt = models.TextField(blank=True)

    api_key = models.CharField(max_length=512, blank=True, editable=False)

    embedding_dim = models.PositiveIntegerField(default=1536)

    is_active = models.BooleanField(default=False)
    is_fallback = models.BooleanField(default=False)
    fallback_order = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["agent_type", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["agent_type"],
                condition=models.Q(is_active=True),
                name="unique_active_agent_per_type",
            )
        ]

    def __str__(self) -> str:
        return f"{self.name} ({self.get_agent_type_display()})"

    @property
    def api_key_plain(self) -> str:
        if not self.api_key:
            return ""
        try:
            return decrypt_secret(self.api_key)
        except Exception:
            return ""

    @property
    def has_api_key(self) -> bool:
        return bool(self.api_key)

    @property
    def api_key_masked(self) -> str:
        plain = self.api_key_plain
        if not plain:
            return ""
        if len(plain) <= 8:
            return "•" * len(plain)
        return f"{plain[:3]}…{plain[-4:]}"


class PlatformConfig(models.Model):
    key = models.CharField(max_length=64, unique=True, default="default")
    data = models.JSONField(default=dict, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return self.key
