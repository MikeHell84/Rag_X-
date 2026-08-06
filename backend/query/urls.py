from django.urls import path

from . import views

urlpatterns = [
    path("query/", views.QueryView.as_view(), name="query"),
    path("query/<str:task_id>/", views.QueryResultView.as_view(), name="query-result"),
    path("query/<str:task_id>/stream/", views.QueryStreamView.as_view(), name="query-stream"),
    path("query-logs/<int:log_id>/feedback/", views.QueryLogFeedbackView.as_view(), name="query-log-feedback"),
    path("query-logs/", views.QueryLogListView.as_view(), name="query-log-list"),
]
