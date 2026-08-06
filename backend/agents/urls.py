from django.urls import path
from rest_framework.routers import DefaultRouter

from . import views

router = DefaultRouter()
router.register("agents", views.AgentViewSet, basename="agent")

urlpatterns = router.urls + [
    path("platform-config/", views.PlatformConfigView.as_view(), name="platform-config"),
    path("chat-agents/", views.ChatAgentsView.as_view(), name="chat-agents"),
]
