from django.urls import path

from .views import (
    CommunityConversationsView,
    ConversationDetailView,
    ConversationMessagesView,
    ConversationDeleteView,
    MessageDeleteView,
    MessageBulkDeleteView,
    MessageEditView,
    MessageReactView,
    MarkConversationReadView,
    UnreadConversationsCountView,
)

urlpatterns = [
    path('community/<int:community_id>/', CommunityConversationsView.as_view()),
    path('unread/', UnreadConversationsCountView.as_view()),
    path('<int:conversation_id>/', ConversationDetailView.as_view()),
    path('<int:conversation_id>/messages/', ConversationMessagesView.as_view()),
    path('<int:conversation_id>/read/', MarkConversationReadView.as_view()),
    path('<int:conversation_id>/delete/', ConversationDeleteView.as_view()),
    path('messages/<int:message_id>/delete/', MessageDeleteView.as_view()),
    path('<int:conversation_id>/messages/bulk-delete/', MessageBulkDeleteView.as_view()),
    path('messages/<int:message_id>/edit/', MessageEditView.as_view()),
    path('messages/<int:message_id>/react/', MessageReactView.as_view()),
]
