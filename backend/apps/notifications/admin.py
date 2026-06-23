from django.contrib import admin
from .models import Notification, NotificationDeadLetter


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('user', 'notification_type', 'title', 'is_read', 'created_at')
    list_filter = ('notification_type', 'is_read')
    search_fields = ('title', 'message')
    actions = ['mark_as_read']

    def mark_as_read(self, request, queryset):
        queryset.update(is_read=True)
    mark_as_read.short_description = "Mark selected as read"


@admin.register(NotificationDeadLetter)
class NotificationDeadLetterAdmin(admin.ModelAdmin):
    list_display  = ('created_at', 'channel', 'notification_type', 'user_id', 'resolved_at')
    list_filter   = ('channel', 'notification_type', 'created_at')
    search_fields = ('error',)
    date_hierarchy = 'created_at'
    readonly_fields = ('created_at',)
