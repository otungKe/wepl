from django.contrib import admin

from .models import Community, CommunityJoinRequest, CommunityMembership


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display    = ("name", "created_by", "category", "is_private",
                       "has_welfare_fund", "has_shares_fund", "created_at")
    list_filter     = ("is_private", "category", "has_welfare_fund", "has_shares_fund")
    search_fields   = ("name", "description", "invite_code")
    readonly_fields = ("invite_code", "created_at")


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display  = ("user", "community", "role", "is_active", "joined_at")
    list_filter   = ("role", "is_active")
    search_fields = ("user__phone_number", "community__name")


@admin.register(CommunityJoinRequest)
class CommunityJoinRequestAdmin(admin.ModelAdmin):
    list_display    = ("requester", "community", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter     = ("status",)
    search_fields   = ("requester__phone_number", "community__name")
    readonly_fields = ("created_at",)
