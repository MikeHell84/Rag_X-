from django.urls import include, path

from .views import HealthView, MetricsView

urlpatterns = [
    path("health/", HealthView.as_view(), name="health"),
    path("metrics/", MetricsView.as_view(), name="metrics"),
    path("", include("documents.urls")),
    path("", include("query.urls")),
    path("", include("agents.urls")),
]
