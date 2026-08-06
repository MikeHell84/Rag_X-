from rest_framework import serializers

from .crypto import encrypt_secret
from .models import Agent, PlatformConfig
from .services import PLATFORM_DEFAULTS


class AgentSerializer(serializers.ModelSerializer):
    agent_type_display = serializers.CharField(source="get_agent_type_display", read_only=True)
    has_api_key = serializers.BooleanField(read_only=True)
    api_key_masked = serializers.CharField(read_only=True)
    api_key = serializers.CharField(
        write_only=True,
        required=False,
        allow_blank=True,
        trim_whitespace=False,
        max_length=512,
        style={"input_type": "password"},
    )

    class Meta:
        model = Agent
        fields = [
            "id",
            "name",
            "agent_type",
            "agent_type_display",
            "provider",
            "model",
            "base_url",
            "description",
            "temperature",
            "max_tokens",
            "top_k",
            "system_prompt",
            "embedding_dim",
            "api_key",
            "has_api_key",
            "api_key_masked",
            "is_active",
            "is_fallback",
            "fallback_order",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]
        extra_kwargs = {
            "agent_type": {"validators": []},
        }

    def validate(self, attrs):
        agent_type = attrs.get("agent_type", getattr(self.instance, "agent_type", None))
        if agent_type not in ("chat", "embedding", "reranker"):
            raise serializers.ValidationError("agent_type inválido")
        return attrs

    def _store_api_key(self, agent: Agent, plain) -> None:
        if plain is None:
            return
        agent.api_key = encrypt_secret(plain)
        agent.save(update_fields=["api_key", "updated_at"])

    def create(self, validated_data):
        plain = validated_data.pop("api_key", None)
        agent = super().create(validated_data)
        self._store_api_key(agent, plain)
        return agent

    def update(self, instance, validated_data):
        plain = validated_data.pop("api_key", None)
        instance = super().update(instance, validated_data)
        self._store_api_key(instance, plain)
        return instance


class PlatformConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = PlatformConfig
        fields = ["data"]

    def validate_data(self, value):
        allowed = set(PLATFORM_DEFAULTS)
        unknown = set(value) - allowed
        if unknown:
            raise serializers.ValidationError(f"claves desconocidas: {sorted(unknown)}")
        for key in ("chunk_size", "chunk_overlap", "hybrid_top_k", "rerank_top_k", "embed_batch_size", "max_context_tokens"):
            if key in value and value[key] is not None and value[key] <= 0:
                raise serializers.ValidationError(f"{key} debe ser mayor que 0")
        if "use_semantic_guard" in value and not isinstance(value["use_semantic_guard"], bool):
            raise serializers.ValidationError("use_semantic_guard debe ser booleano")
        return value
