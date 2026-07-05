from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.utils import timezone
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from unfold.admin import ModelAdmin as UnfoldModelAdmin

from .models import User, KYCProfile, VerificationRequest, PaymentMethod


# ─────────────────────────────────────────────────────────────
# USER ADMIN
# ─────────────────────────────────────────────────────────────

@admin.action(description='Deactivate selected users (blocks login)', permissions=['change'])
def deactivate_users(modeladmin, request, queryset):
    n = queryset.update(is_active=False)
    modeladmin.message_user(request, f"{n} user(s) deactivated.")


@admin.action(description='Reactivate selected users', permissions=['change'])
def activate_users(modeladmin, request, queryset):
    n = queryset.update(is_active=True)
    modeladmin.message_user(request, f"{n} user(s) reactivated.")


@admin.action(description='Reset PIN (user must set a new one)', permissions=['change'])
def reset_pin(modeladmin, request, queryset):
    n = queryset.update(pin='', is_pin_set=False)
    modeladmin.message_user(request, f"{n} user(s) PIN cleared — they'll set a new PIN on next login.")


@admin.register(User)
class UserAdmin(BaseUserAdmin, UnfoldModelAdmin):
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


@admin.action(description='Approve selected KYC submissions', permissions=['change'])
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


@admin.action(description='Reject selected KYC submissions', permissions=['change'])
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
    """Render a KYC document preview for the admin, degrading legibly:
    - no file on the record → '—'
    - file recorded but missing from storage (e.g. object storage not enabled,
      so uploads landed on an ephemeral disk and were lost) → a clear warning
      with the stored path, instead of a silent broken-image icon
    - URL cannot be built → a warning with the error
    """
    if not file:
        return '—'
    try:
        if not file.storage.exists(file.name):
            return format_html(
                '<span style="color:#C0392B">⚠ File not found in storage: <code>{}</code><br>'
                '<small>Uploads are not being stored durably — enable object storage '
                '(USE_S3) so KYC documents persist.</small></span>',
                file.name,
            )
    except Exception:
        pass  # some backends can't cheaply check existence — let the browser try
    try:
        url = file.url
    except Exception as exc:
        return format_html('<span style="color:#C0392B">⚠ Cannot build URL for <code>{}</code> ({})</span>',
                           file.name, str(exc))
    return format_html(
        '<a href="{0}" target="_blank"><img src="{0}" '
        'style="max-height:220px;max-width:340px;border:1px solid #ccc;border-radius:6px"/></a>',
        url,
    )


@admin.register(KYCProfile)
class KYCProfileAdmin(UnfoldModelAdmin):
    list_display  = ('user', 'full_name', 'id_number', 'county', 'status', 'submitted_at', 'reviewed_at')
    list_filter   = ('status', 'county', 'source_of_income', 'expected_monthly_income')
    search_fields = ('user__phone_number', 'given_names', 'surname', 'id_number')
    ordering      = ('-submitted_at',)
    readonly_fields = (
        'user', 'submitted_at', 'updated_at',
        'id_front_preview', 'id_back_preview', 'selfie_preview',
        'verification_summary',
    )
    actions = [approve_kyc, reject_kyc]

    fieldsets = (
        ('Applicant',   {'fields': ('user', 'given_names', 'surname', 'id_number', 'kra_pin', 'date_of_birth', 'email')}),
        ('Documents',   {'fields': ('id_front_preview', 'id_back_preview', 'selfie_preview')}),
        ('Automated checks', {'fields': ('verification_summary',)}),
        ('Location',    {'fields': ('county', 'physical_address')}),
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

    @admin.display(description='Provider & OCR cross-check')
    def verification_summary(self, obj):
        """Advisory signals for the reviewer: which checker ran, and how the
        in-house OCR of the ID scan compares to the typed values. Mismatches are
        flagged in red — they are hints for manual review, not a verdict."""
        provider = obj.verification_provider or '—'
        state    = obj.verification_state or '—'
        checked  = obj.verification_checked_at.strftime('%Y-%m-%d %H:%M') if obj.verification_checked_at else '—'
        ocr = (obj.verification_detail or {}).get('ocr') or {}

        def _flag(match, read):
            # match: True (agrees) / False (disagrees) / None (couldn't read)
            if match is True:
                return format_html('<span style="color:#1D7A45">✓ matches</span> ({})', read or '')
            if match is False:
                return format_html('<span style="color:#C0392B;font-weight:700">✗ MISMATCH</span> (scan read: {})', read or '—')
            return mark_safe('<span style="color:#8a8a8a">— not read from scan</span>')

        if not ocr:
            ocr_html = mark_safe('<em style="color:#8a8a8a">No OCR result recorded '
                                 '(scan unreadable or OCR not enabled — verify manually).</em>')
        else:
            detected = ocr.get('detected')
            ocr_html = format_html(
                '<div style="line-height:1.7">'
                '<b>Kenyan ID detected:</b> {}<br>'
                '<b>ID number:</b> {}<br>'
                '<b>Date of birth:</b> {}<br>'
                '<b>OCR engine:</b> {}'
                '</div>',
                mark_safe('<span style="color:#1D7A45">yes</span>') if detected
                else mark_safe('<span style="color:#C0392B">no — verify the image is a valid ID</span>'),
                _flag(ocr.get('id_number_match'), ocr.get('id_number_read')),
                _flag(ocr.get('dob_match'), ocr.get('dob_read')),
                ocr.get('engine', '—'),
            )

        return format_html(
            '<div style="max-width:520px">'
            '<div style="margin-bottom:8px"><b>Checker:</b> {} &nbsp;·&nbsp; '
            '<b>Result:</b> {} &nbsp;·&nbsp; <b>Checked:</b> {}</div>{}</div>',
            provider, state, checked, ocr_html,
        )

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


# ─────────────────────────────────────────────────────────────
# VERIFICATION REQUESTS ADMIN
# ─────────────────────────────────────────────────────────────

def _notify_verification_request(vreq, *, resolved=False):
    """Notify the user that a verification request was raised or resolved."""
    from apps.core.events import emit
    if resolved:
        emit(
            'verification_request_resolved',
            user_id=vreq.user_id,
            title='Verification updated',
            message=f'"{vreq.title}" has been resolved.'
                    + (f' {vreq.review_note}' if vreq.review_note else ''),
        )
    else:
        emit(
            'verification_request',
            user_id=vreq.user_id,
            title='Action needed: verification',
            message=f'{vreq.title} — open your Verification Center to respond.',
        )


@admin.action(description='Mark selected requests resolved (notify user)', permissions=['change'])
def resolve_requests(modeladmin, request, queryset):
    n = 0
    for vreq in queryset.exclude(status=VerificationRequest.Status.RESOLVED):
        vreq.status = VerificationRequest.Status.RESOLVED
        vreq.resolved_at = timezone.now()
        vreq.save(update_fields=['status', 'resolved_at'])
        _notify_verification_request(vreq, resolved=True)
        n += 1
    modeladmin.message_user(request, f"{n} request(s) resolved and user(s) notified.")


@admin.register(VerificationRequest)
class VerificationRequestAdmin(UnfoldModelAdmin):
    list_display  = ('id', 'user', 'kind', 'title', 'status', 'created_at')
    list_filter   = ('status', 'kind', 'created_at')
    search_fields = ('user__phone_number', 'title', 'detail')
    readonly_fields = ('response_note', 'document', 'responded_at', 'created_at', 'created_by')
    actions = [resolve_requests]

    def save_model(self, request, obj, form, change):
        creating = not change
        if creating and not obj.created_by_id:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)
        # Notify the user when a new request is raised against them.
        if creating and obj.status == VerificationRequest.Status.OPEN:
            _notify_verification_request(obj)


@admin.register(PaymentMethod)
class PaymentMethodAdmin(UnfoldModelAdmin):
    list_display  = ('id', 'user', 'kind', 'display', 'is_default', 'created_at')
    list_filter   = ('kind', 'is_default', 'created_at')
    search_fields = ('user__phone_number', 'mpesa_phone', 'label')
    readonly_fields = ('created_at',)
