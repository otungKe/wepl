from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone

from .models import User, KYCProfile


# ─────────────────────────────────────────────────────────────
# USER ADMIN
# ─────────────────────────────────────────────────────────────

@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display  = ('phone_number', 'name', 'is_phone_verified', 'is_pin_set', 'is_staff', 'date_joined')
    list_filter   = ('is_phone_verified', 'is_pin_set', 'is_staff', 'is_superuser')
    search_fields = ('phone_number', 'name')
    ordering      = ('-date_joined',)

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

@admin.action(description='Approve selected KYC submissions')
def approve_kyc(modeladmin, request, queryset):
    queryset.filter(status='pending').update(
        status='approved',
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
        rejection_reason='',
    )


@admin.action(description='Reject selected KYC submissions')
def reject_kyc(modeladmin, request, queryset):
    queryset.filter(status='pending').update(
        status='rejected',
        reviewed_by=request.user,
        reviewed_at=timezone.now(),
    )


@admin.register(KYCProfile)
class KYCProfileAdmin(admin.ModelAdmin):
    list_display  = ('user', 'full_name', 'id_number', 'county', 'status', 'submitted_at', 'reviewed_at')
    list_filter   = ('status', 'county', 'source_of_income', 'expected_monthly_income')
    search_fields = ('user__phone_number', 'given_names', 'surname', 'id_number')
    ordering      = ('-submitted_at',)
    readonly_fields = (
        'user', 'submitted_at', 'updated_at',
        'id_front', 'id_back',   # display as links, not editable
    )
    actions = [approve_kyc, reject_kyc]

    fieldsets = (
        ('Applicant',   {'fields': ('user', 'given_names', 'surname', 'id_number', 'date_of_birth', 'email')}),
        ('Documents',   {'fields': ('id_front', 'id_back')}),
        ('Location',    {'fields': ('county', 'sub_county')}),
        ('Financials',  {'fields': ('occupation', 'source_of_income', 'expected_monthly_income')}),
        ('Review',      {'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')}),
        ('Timestamps',  {'fields': ('submitted_at', 'updated_at')}),
    )
