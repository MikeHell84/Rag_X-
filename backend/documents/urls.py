from django.urls import path

from . import views

urlpatterns = [
    path("documents/upload/", views.DocumentUploadView.as_view(), name="document-upload"),
    path("documents/from-url/", views.DocumentFromUrlView.as_view(), name="document-from-url"),
    path("documents/reindex/", views.DocumentReindexView.as_view(), name="document-reindex"),
    path("documents/<int:document_id>/retry/", views.DocumentRetryView.as_view(), name="document-retry"),
    path("documents/<int:document_id>/", views.DocumentDetailView.as_view(), name="document-detail"),
    path("documents/", views.DocumentListView.as_view(), name="document-list"),
    path("conversations/", views.ConversationView.as_view(), name="conversation-list"),
    path("conversations/<int:conversation_id>/", views.ConversationView.as_view(), name="conversation-detail"),
    path("conversations/<int:conversation_id>/messages/", views.ConversationMessageView.as_view(), name="conversation-messages"),
    path("cleanup/", views.DataCleanupView.as_view(), name="data-cleanup"),
    path("topics/<int:topic_id>/", views.TopicListView.as_view(), name="topic-detail"),
    path("topics/", views.TopicListView.as_view(), name="topic-list"),
]
