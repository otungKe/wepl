from django.contrib import admin
from django.core.exceptions import ValidationError

from .models import Community, CommunityJoinRequest, CommunityMembership


@admin.action(description='Suspend selected communities (ops freeze)', permissions=['change'])
def suspend_communities(modeladmin, request, queryset):
    """Compliance/fraud freeze: joins, money-object creation and new
    conversations stop; records stay readable. Audited per community."""
    from .services import CommunityService
    n = skipped = 0
    for community in queryset:
        try:
            CommunityService.suspend_community(
                community, actor=request.user, reason='suspended via admin action')
            n += 1
        except ValidationError:
            skipped += 1
    msg = f"{n} community(ies) suspended."
    if skipped:
        msg += f" Skipped {skipped} already suspended."
    modeladmin.message_user(request, msg)


@admin.action(description='Lift suspension on selected communities', permissions=['change'])
def unsuspend_communities(modeladmin, request, queryset):
    from .services import CommunityService
    n = skipped = 0
    for community in queryset:
        try:
            CommunityService.unsuspend_community(
                community, actor=request.user, reason='unsuspended via admin action')
            n += 1
        except ValidationError:
            skipped += 1
    msg = f"{n} community(ies) reactivated."
    if skipped:
        msg += f" Skipped {skipped} not suspended."
    modeladmin.message_user(request, msg)


@admin.register(Community)
class CommunityAdmin(admin.ModelAdmin):
    list_display    = ("name", "created_by", "category", "status", "is_private",
                       "has_welfare_fund", "has_shares_fund", "created_at")
    list_filter     = ("status", "is_private", "category", "has_welfare_fund", "has_shares_fund")
    search_fields   = ("name", "description", "invite_code")
    readonly_fields = ("invite_code", "created_at", "status")  # status moves via actions only
    actions         = [suspend_communities, unsuspend_communities]


@admin.register(CommunityMembership)
class CommunityMembershipAdmin(admin.ModelAdmin):
    list_display  = ("user", "community", "role", "is_active", "joined_at", "rejoined_at")
    list_filter   = ("role", "is_active")
    search_fields = ("user__phone_number", "community__name")


@admin.register(CommunityJoinRequest)
class CommunityJoinRequestAdmin(admin.ModelAdmin):
    list_display    = ("requester", "community", "status", "created_at", "reviewed_by", "reviewed_at")
    list_filter     = ("status",)
    search_fields   = ("requester__phone_number", "community__name")
    readonly_fields = ("created_at",)
