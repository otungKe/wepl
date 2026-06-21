from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html

from .models import User, KYCProfile


# ─────────────────────────────────────────────────────────────
# USER ADMIN
# ─────────────────────────────────────────────────────────────

@admin.action(description='Deactivate selected users (blocks login)')
def deactivate_users(modeladmin, request, queryset):
    n = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{n} user(s) deactivated.")


@admin.action(description='Reactivate selected users')
def activate_users(modeladmin, request, queryset):
    n = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{n} user(s) reactivated.")


@admin.action(description='Reset PIN (user must set a new one)')
def reset_pin(modeladmin, request, queryset):
    n = queryset.update(pin='', is_pin_set=False)
    modeladmin.message_user(request, f"{n} user(s) PIN cleared — they'll set a new PIN on next login.")


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('phone_number', 'name', 'is_phone_verified', 'is_pin_set', 'is_active', 'is_staff', 'date_joined')
    list_filter   = ('is_active', 'is_phone_verified', 'is_pin_set', 'is_staff', 'is_superuser')
    search_fields = ('phone_number', 'name')
    ordering      = ('-date_joined',)
    actions       = [deactivate_users, activate_users, reset_pin]

    fieldsets = (
        (None,          {'fields': ('phone_number', 'pin')}),
        ('Personal',    {'fields': ('name', 'bio', 'profile_photo')}),
        ('Status',      {'fields': ('is_phone_verified', 'is_pin_set')}),
        ('Permissions', {'fields': ('is_active', 'is_staff', 'is_superuser', 'groups', 'user_permissions')}),
        ('Dates',       {'fields': ('last_login', 'date_joined')}),
    )
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields':  ('phone_number', 'password1', 'password2'),
        }),
    )

    # phone_number is the USERNAME_FIELD
    USERNAME_FIELD = 'phone_number'


# ─────────────────────────────────────────────────────────────
# KYC ADMIN
# ─────────────────────────────────────────────────────────────

def _notify_kyc_decision(kyc):
    """Tell the applicant their KYC was approved/rejected (in-app notification).

    Goes through the durable event bus, so it survives crashes and reaches the
    user's device via the normal notification pipeline.
    """
    from apps.core.events import emit

    if kyc.status == 'approved':
        emit(
            'kyc_approved',
            user_id=kyc.user_id,
            title='Identity verified ✅',
            message='Your KYC has been approved — you now have full access to '
                    'payments, contributions, and community features.',
        )
    elif kyc.status == 'rejected':
        reason = kyc.rejection_reason or 'Please re-submit your documents.'
        emit(
            'kyc_rejected',
            user_id=kyc.user_id,
            title='KYC needs attention',
            message=f'Your identity verification was not approved. {reason}',
        )


@admin.action(description='Approve selected KYC submissions')
def approve_kyc(modeladmin, request, queryset):
    n = 0
    for kyc in queryset.filter(status='pending'):
        kyc.status          = 'approved'
        kyc.reviewed_by     = request.user
        kyc.reviewed_at     = timezone.now()
        kyc.rejection_reason = ''
        kyc.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])
        _notify_kyc_decision(kyc)
        n += 1
    modeladmin.message_user(request, f"{n} KYC submission(s) approved and applicant(s) notified.")


@admin.action(description='Reject selected KYC submissions')
def reject_kyc(modeladmin, request, queryset):
    n = 0
    for kyc in queryset.filter(status='pending'):
        kyc.status      = 'rejected'
        kyc.reviewed_by = request.user
        kyc.reviewed_at = timezone.now()
        if not kyc.rejection_reason:
            kyc.rejection_reason = (
                'Your documents could not be verified. Please re-submit clear '
                'photos of your ID.'
            )
        kyc.save(update_fields=['status', 'reviewed_by', 'reviewed_at', 'rejection_reason'])
        _notify_kyc_decision(kyc)
        n += 1
    modeladmin.message_user(
        request,
        f"{n} KYC submission(s) rejected and applicant(s) notified. "
        f"To give a specific reason, open the record and set 'rejection reason' before saving.",
    )


def _img(file):
    if not file:
        return '—'
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" '
        'style="max-height:220px;max-width:340px;border:1px solid #ccc;border-radius:6px"/></a>',
        file.url,
    )


@admin.register(KYCProfile)
class KYCProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'full_name', 'id_number', 'county', 'status', 'submitted_at', 'reviewed_at')
    list_filter   = ('status', 'county', 'source_of_income', 'expected_monthly_income')
    search_fields = ('user__phone_number', 'given_names', 'surname', 'id_number')
    ordering      = ('-submitted_at',)
    readonly_fields = (
        'user', 'submitted_at', 'updated_at',
        'id_front_preview', 'id_back_preview', 'selfie_preview',
    )
    actions = [approve_kyc, reject_kyc]

    fieldsets = (
        ('Applicant',   {'fields': ('user', 'given_names', 'surname', 'id_number', 'date_of_birth', 'email')}),
        ('Documents',   {'fields': ('id_front_preview', 'id_back_preview', 'selfie_preview')}),
        ('Location',    {'fields': ('county', 'sub_county')}),
        ('Financials',  {'fields': ('occupation', 'source_of_income', 'expected_monthly_income')}),
        ('Review',      {'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')}),
        ('Timestamps',  {'fields': ('submitted_at', 'updated_at')}),
    )

    @admin.display(description='ID front')
    def id_front_preview(self, obj):
        return _img(obj.id_front)

    @admin.display(description='ID back')
    def id_back_preview(self, obj):
        return _img(obj.id_back)

    @admin.display(description='Selfie')
    def selfie_preview(self, obj):
        return _img(obj.selfie)

    def save_model(self, request, obj, form, change):
        """When an admin sets status to approved/rejected via the form, stamp the
        reviewer/time and notify the applicant — so a decision with a typed
        rejection reason behaves like the bulk actions."""
        decision = 'status' in form.changed_data and obj.status in ('approved', 'rejected')
        if decision:
            obj.reviewed_by = request.user
            obj.reviewed_at = timezone.now()
            if obj.status == 'approved':
                obj.rejection_reason = ''
        super().save_model(request, obj, form, change)
        if decision:
            _notify_kyc_decision(obj)
