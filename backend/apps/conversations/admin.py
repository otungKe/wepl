from django.contrib import admin
from .models import Conversation, Message


@admin.register(Conversation)
class ConversationAdmin(admin.ModelAdmin):
    list_display = ('topic', 'community', 'created_by', 'created_at')
    list_filter = ('community',)
    search_fields = ('topic',)


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('conversation', 'sender', 'message_type', 'created_at', 'is_deleted')
    list_filter = ('message_type', 'is_deleted')
    search_fields = ('content',)
