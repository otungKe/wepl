from django.contrib import admin
from .models import Community, CommunityMembership


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_by', 'is_private', 'created_at')
    list_filter = ('is_private',)
    search_fields = ('name', 'description')


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display = ('user', 'community', 'role', 'is_active', 'joined_at')
    list_filter = ('role', 'is_active')
