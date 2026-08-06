from django.contrib import admin

from .models import Agent, PlatformConfig


@admin.register(Agent)
class AgentAdmin(admin.ModelAdmin):
    list_display = ("name", "agent_type", "provider", "model", "temperature", "is_active")
    list_filter = ("agent_type", "is_active", "provider")
    search_fields = ("name", "model")


@admin.register(PlatformConfig)
class PlatformConfigAdmin(admin.ModelAdmin):
    list_display = ("key", "updated_at")
