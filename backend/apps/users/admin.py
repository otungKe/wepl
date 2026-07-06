from django import forms
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
    from apps.verification import service as case_service
    n = 0
    for kyc in queryset.filter(status='pending'):
        try:
            case_service.decide(kyc, 'approve', actor_label='manual (admin)',
                                reviewer_user=request.user)
        except case_service.IllegalTransition:
            continue
        n += 1
    modeladmin.message_user(request, f"{n} KYC submission(s) approved and applicant(s) notified.")


@admin.action(description='Reject selected KYC submissions', permissions=['change'])
def reject_kyc(modeladmin, request, queryset):
    from apps.verification import service as case_service
    n = 0
    for kyc in queryset.filter(status='pending'):
        try:
            case_service.decide(kyc, 'reject', actor_label='manual (admin)',
                                reviewer_user=request.user,
                                reason=kyc.rejection_reason)
        except case_service.IllegalTransition:
            continue
        n += 1
    modeladmin.message_user(
        request,
        f"{n} KYC submission(s) rejected and applicant(s) notified. "
        f"To give a specific reason, open the record and set 'rejection reason' before saving.",
    )


def _notify_resubmission_request(kyc):
    """Tell the user which KYC items they've been asked to re-provide, and send
    them to the targeted re-submission screen (they don't re-fill the whole form)."""
    from apps.core.events import emit
    labels = dict(KYCProfile.RESUBMITTABLE_ITEMS)
    items = ', '.join(labels.get(k, k) for k in (kyc.resubmission_requested or []))
    emit(
        'kyc_resubmission_requested',
        user_id=kyc.user_id,
        title='Action needed: re-submit KYC items',
        message=f'Please re-submit the following in WEPL: {items}. '
                f'You only need to provide these — the rest of your details stay as they are.',
    )


@admin.action(description='Request document re-submission (front, back & selfie)', permissions=['change'])
def request_kyc_resubmission(modeladmin, request, queryset):
    """Ask selected users to re-provide their ID photos — the common case (e.g.
    unclear or lost documents). Sets the targeted-re-submission list to the three
    documents and notifies; it does NOT change the KYC status, so the user keeps
    any existing access and only tops up the requested items via the app. To ask
    for a different set of items, open the record and edit
    "Requested for re-submission" instead.
    """
    from apps.verification import service as case_service
    n = skipped = 0
    for kyc in queryset:
        try:
            case_service.decide(kyc, 'request_info', actor_label='manual (admin)',
                                reviewer_user=request.user,
                                items=['id_front', 'id_back', 'selfie'])
        except case_service.IllegalTransition:
            skipped += 1   # approved cases are closed to re-submission
            continue
        n += 1
    msg = (f"Requested document re-submission from {n} user(s). They have been "
           f"notified and can top up just those items in the app.")
    if skipped:
        msg += f" Skipped {skipped} approved case(s) — approved KYC is closed to re-submission."
    modeladmin.message_user(request, msg)


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


class KYCAdminForm(forms.ModelForm):
    """Renders `resubmission_requested` (a JSON list) as a friendly checkbox set
    so a reviewer can pick exactly which items to ask the user to re-provide."""
    resubmission_requested = forms.MultipleChoiceField(
        choices=KYCProfile.RESUBMITTABLE_ITEMS,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Requested for re-submission',
        help_text='Tick the items the user must re-provide. They top up only '
                  'these in the app — the rest of their KYC stays as-is. Saving '
                  'with any ticked notifies the user.',
    )

    class Meta:
        model = KYCProfile
        fields = '__all__'


@admin.register(KYCProfile)
class KYCProfileAdmin(UnfoldModelAdmin):
    form = KYCAdminForm
    list_display  = ('user', 'full_name', 'id_number', 'county', 'status', 'email_verified', 'submitted_at', 'reviewed_at')
    list_filter   = ('status', 'email_verified', 'county', 'source_of_income', 'expected_monthly_income')
    search_fields = ('user__phone_number', 'given_names', 'surname', 'id_number', 'kra_pin')
    ordering      = ('-submitted_at',)
    readonly_fields = (
        'user', 'submitted_at', 'updated_at', 'email_verified',
        'id_front_preview', 'id_back_preview', 'selfie_preview',
        'verification_summary',
    )
    actions = [approve_kyc, reject_kyc, request_kyc_resubmission]

    fieldsets = (
        ('Applicant',   {'fields': ('user', 'given_names', 'surname', 'id_number', 'kra_pin', 'date_of_birth', 'email', 'email_verified', 'referral_code')}),
        ('Documents',   {'fields': ('id_front_preview', 'id_back_preview', 'selfie_preview')}),
        ('Automated checks', {'fields': ('verification_summary',)}),
        ('Location',    {'fields': ('county', 'physical_address')}),
        ('Financials',  {'fields': ('occupation', 'source_of_income', 'expected_monthly_income')}),
        ('Review',      {'fields': ('status', 'rejection_reason', 'reviewed_by', 'reviewed_at')}),
        ('Ask user to re-submit', {
            'fields': ('resubmission_requested',),
            'description': 'Tick items to request a targeted re-submission — the '
                           'user re-provides only these, not the whole form.',
        }),
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
        """When an admin sets status to approved/rejected (or asks for items to
        be re-submitted) via the form, apply it through the case state machine
        (apps.verification.service) so the decision is evented, projected, and
        notified exactly like the bulk actions and the ops console."""
        from apps.verification import service as case_service

        decision = 'status' in form.changed_data and obj.status in ('approved', 'rejected')
        super().save_model(request, obj, form, change)
        if decision:
            action = 'approve' if obj.status == 'approved' else 'reject'
            try:
                case_service.decide(obj, action, actor_label='manual (admin)',
                                    reviewer_user=request.user,
                                    reason=obj.rejection_reason)
            except case_service.IllegalTransition:
                pass  # form save already reflects the state; nothing to advance
        # A reviewer ticked items to re-request via the form → event + notify.
        # Approved cases refuse (closed to re-submission) — nothing to notify.
        if 'resubmission_requested' in form.changed_data and obj.resubmission_requested:
            try:
                case_service.decide(obj, 'request_info', actor_label='manual (admin)',
                                    reviewer_user=request.user,
                                    items=obj.resubmission_requested)
            except case_service.IllegalTransition:
                obj.resubmission_requested = []
                obj.save(update_fields=['resubmission_requested'])


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
