from django.contrib import admin

from .models import Chunk, Document, QueryLog, Conversation, ConversationMessage


@admin.register(Document)
class DocumentAdmin(admin.ModelAdmin):
    list_display = ("title", "source_type", "status", "total_chunks", "created_at")
    list_filter = ("status", "source_type")
    search_fields = ("title",)


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    list_display = ("document", "index", "section", "token_count")
    list_filter = ("document",)


@admin.register(QueryLog)
class QueryLogAdmin(admin.ModelAdmin):
    list_display = ("query_text", "llm_model", "total_cost_usd", "latency_ms", "created_at")


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ("title", "topic", "agent", "session_key", "updated_at")
    list_filter = ("topic", "visibility")
    search_fields = ("title", "topic", "session_key")


@admin.register(ConversationMessage)
class ConversationMessageAdmin(admin.ModelAdmin):
    list_display = ("conversation", "role", "content", "created_at")
    list_filter = ("role", "conversation__topic")
    search_fields = ("content",)
    raw_id_fields = ("conversation",)
