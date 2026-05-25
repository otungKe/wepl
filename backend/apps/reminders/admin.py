from django.contrib import admin
from .models import Reminder


@admin.register(Reminder)
class ReminderAdmin(admin.ModelAdmin):
    list_display  = ('user', 'title', 'reminder_type', 'recurrence', 'next_fire_at', 'is_active', 'send_count')
    list_filter   = ('reminder_type', 'recurrence', 'is_active')
    search_fields = ('user__phone_number', 'title')
    ordering      = ('next_fire_at',)
    readonly_fields = ('send_count', 'last_sent_at', 'created_at', 'updated_at')
