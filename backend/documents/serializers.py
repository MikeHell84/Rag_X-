from rest_framework import serializers

from .models import Chunk, Document, QueryLog, Conversation, ConversationMessage


class DocumentSerializer(serializers.ModelSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    task_id = serializers.CharField(source="metadata.task_id", read_only=True)
    url = serializers.CharField(source="metadata.url", read_only=True)
    markdown_url = serializers.SerializerMethodField()

    class Meta:
        model = Document
        fields = [
            "id",
            "title",
            "source_type",
            "status",
            "status_display",
            "total_chunks",
            "total_tokens",
            "error_message",
            "task_id",
            "topic",
            "url",
            "markdown_url",
            "created_at",
            "updated_at",
        ]

    def get_markdown_url(self, obj) -> str | None:
        if not obj.file:
            return None
        try:
            url = obj.file.url
        except Exception:
            return None
        return url


class DocumentCreateSerializer(serializers.ModelSerializer):
    file = serializers.FileField()

    class Meta:
        model = Document
        fields = ["title", "file", "source_type", "content_hash", "topic"]

    def validate(self, attrs):
        ext = attrs["file"].name.rsplit(".", 1)[-1].lower()
        allowed = {k: v for v, k in Document.source_type.field.choices}
        mapping = {"pdf": "pdf", "docx": "docx", "md": "md", "txt": "txt"}
        if ext not in mapping:
            raise serializers.ValidationError(f"Extensión .{ext} no soportada (pdf, docx, md, txt)")
        attrs["source_type"] = mapping[ext]
        return attrs


class ChunkSerializer(serializers.ModelSerializer):
    class Meta:
        model = Chunk
        fields = ["id", "index", "section", "page", "content", "token_count"]


class QueryLogSerializer(serializers.ModelSerializer):
    agent_name = serializers.CharField(source="used_agent.name", read_only=True)
    agent_model = serializers.CharField(source="used_agent.model", read_only=True)

    class Meta:
        model = QueryLog
        fields = [
            "id",
            "query_text",
            "embedding_model",
            "llm_model",
            "candidate_count",
            "rerank_count",
            "tokens_prompt",
            "tokens_completion",
            "total_cost_usd",
            "latency_ms",
            "answer",
            "feedback",
            "used_agent",
            "agent_name",
            "agent_model",
            "created_at",
            "updated_at",
        ]


class ConversationMessageSerializer(serializers.ModelSerializer):
    class Meta:
        model = ConversationMessage
        fields = ["id", "role", "content", "created_at"]
        read_only_fields = ["id", "created_at"]


class ConversationSerializer(serializers.ModelSerializer):
    messages = ConversationMessageSerializer(many=True, read_only=True)
    agent_name = serializers.CharField(source="agent.name", read_only=True, allow_null=True)
    agent_model = serializers.CharField(source="agent.model", read_only=True, allow_null=True)

    class Meta:
        model = Conversation
        fields = [
            "id",
            "title",
            "topic",
            "agent",
            "agent_name",
            "agent_model",
            "visibility",
            "session_key",
            "messages",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "created_at", "updated_at"]

    def create(self, validated_data):
        return Conversation.objects.create(**validated_data)
