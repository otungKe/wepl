import logging

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from .auth import (
    STAGE_ACTIVE, STAGE_OTP_RECOVERY, STAGE_OTP_VERIFIED,
    IsActiveSession, StageRequired, issue_tokens,
)
from .models import KYCProfile, PrivacyPreferences
from .serializers import UserSerializer, KYCSubmitSerializer, KYCStatusSerializer
from .services import UserService, OTPService, PINService

PRIVACY_FIELDS = (
    'phone_visibility', 'photo_visibility', 'contribution_visibility',
    'discoverable', 'show_online_status',
)

logger = logging.getLogger(__name__)

User = get_user_model()


class PINLoginThrottle(AnonRateThrottle):
    """Per-IP rate limit for PIN login — uses the 'pin_login' scope from settings."""
    scope = 'pin_login'


class OTPRequestThrottle(AnonRateThrottle):
    """Per-IP rate limit for OTP requests — uses the 'otp_request' scope from settings."""
    scope = 'otp_request'


# -----------------------------
# 1. REQUEST OTP
# -----------------------------
class RequestOTPView(APIView):
    # Public endpoint — no token required.
    permission_classes = []
    throttle_classes   = [OTPRequestThrottle]

    def post(self, request):

        phone = request.data.get("phone_number", "").strip()

        if not phone:
            return Response(
                {"error": "phone_number is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # NOTE: we intentionally do NOT return is_registered to the caller here.
        # Returning true/false for arbitrary phone numbers lets an unauthenticated
        # attacker enumerate which numbers are registered (user-enumeration oracle).
        # The frontend learns the registration state from the next step:
        # VerifyOTPView returns next_step='set_pin' (new) or 'reset_pin' (existing).
        OTPService.send_otp(phone)
        logger.info("OTP requested for %s", phone)

        return Response({"message": "OTP sent."}, status=status.HTTP_200_OK)


# -----------------------------
# 2. VERIFY OTP → TEMP JWT
# -----------------------------
class VerifyOTPView(APIView):
    # Public endpoint — caller has no token yet; they're proving phone ownership.
    permission_classes = []

    def post(self, request):

        phone = request.data.get("phone_number")
        otp   = request.data.get("otp")

        if not phone or not otp:
            return Response(
                {"error": "phone_number and otp are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        if not OTPService.verify_otp(phone, otp):
            return Response(
                {"error": "Invalid or expired OTP."},
                status=status.HTTP_400_BAD_REQUEST
            )

        user = UserService.get_or_create_user(phone)
        user.is_phone_verified = True
        user.save(update_fields=["is_phone_verified"])

        if user.is_pin_set:
            # Fully-registered user — OTP used as PIN-recovery path.
            # Issue a *recovery* token, not a full session.
            # The frontend should direct them to /pin/reset/ not /pin/set/.
            logger.info("OTP verified (recovery flow) for %s", phone)
            return Response({
                "message":     "OTP verified.",
                **issue_tokens(user, STAGE_OTP_RECOVERY),
                "is_new_user": False,
                "next_step":   "reset_pin",
            }, status=status.HTTP_200_OK)
        else:
            # New user or incomplete onboarding (OTP verified, PIN not yet set).
            logger.info("OTP verified (registration flow) for %s", phone)
            return Response({
                "message":     "OTP verified.",
                **issue_tokens(user, STAGE_OTP_VERIFIED),
                "is_new_user": True,
                "next_step":   "set_pin",
            }, status=status.HTTP_200_OK)


# -----------------------------
# 3. SET PIN (NEW USERS ONLY)
# -----------------------------
class SetPINView(APIView):
    """
    First-time PIN setup for new / not-yet-onboarded users.

    Requires an otp_verified-stage token (issued by VerifyOTPView for new users).
    Blocked for users who already have a PIN — they must use /auth/pin/reset/.
    """

    permission_classes = [StageRequired]
    required_stages    = {STAGE_OTP_VERIFIED}

    def post(self, request):

        if request.user.is_pin_set:
            return Response(
                {"error": "PIN already set. Use /auth/pin/reset/ to change your PIN."},
                status=status.HTTP_409_CONFLICT
            )

        pin = request.data.get("pin")

        if not pin:
            return Response(
                {"error": "PIN is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        PINService.set_pin(request.user, pin)
        logger.info("PIN set for %s — active session issued", request.user.phone_number)

        return Response({
            "message": "PIN set successfully.",
            **issue_tokens(request.user, STAGE_ACTIVE),
            "status":  "active_user",
        }, status=status.HTTP_200_OK)


# -----------------------------
# 4. RESET PIN (RECOVERY)
# -----------------------------
class ResetPINView(APIView):
    """
    PIN reset for users who forgot their PIN.

    Requires a valid JWT with stage='otp_recovery' — issued by
    VerifyOTPView when an already-registered user verifies their OTP.

    Flow:
        POST /auth/otp/request/  →  OTP sent
        POST /auth/otp/verify/   →  {stage: "otp_recovery", next_step: "reset_pin"}
        POST /auth/pin/reset/    →  new PIN set, active JWT returned
    """

    # Requires an otp_recovery-stage token. StageRequired handles the gate so we
    # no longer need the manual _token_stage check in the body.
    permission_classes = [StageRequired]
    required_stages    = {STAGE_OTP_RECOVERY}

    def post(self, request):

        pin = request.data.get("pin")

        if not pin:
            return Response(
                {"error": "PIN is required"},
                status=status.HTTP_400_BAD_REQUEST,
            )

        PINService.set_pin(request.user, pin)
        logger.info("PIN reset for %s — active session issued", request.user.phone_number)

        # Issue a full active session now that recovery is complete.
        return Response({
            "message": "PIN reset successfully.",
            **issue_tokens(request.user, STAGE_ACTIVE),
        }, status=status.HTTP_200_OK)


# -----------------------------
# 4. PIN LOGIN
# -----------------------------
class PINLoginView(APIView):
    # Public endpoint — caller is proving identity, no token exists yet.
    permission_classes = []
    throttle_classes   = [PINLoginThrottle]

    def post(self, request):

        phone = request.data.get("phone_number", "").strip()
        pin   = request.data.get("pin", "").strip()

        if not phone or not pin:
            return Response(
                {"error": "phone_number and pin are required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            user = User.objects.get(phone_number=phone)
        except User.DoesNotExist:
            # Return same message as wrong-PIN to avoid user enumeration
            return Response(
                {"error": "Invalid phone number or PIN."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        if PINService.is_locked(user):
            return Response(
                {"error": "Account temporarily locked due to too many failed PIN attempts. Try again in 30 minutes."},
                status=status.HTTP_429_TOO_MANY_REQUESTS
            )

        if not PINService.verify_pin(user, pin):
            PINService.record_failure(user)
            logger.warning("Failed PIN attempt for %s", phone)
            return Response(
                {"error": "Invalid phone number or PIN."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Successful login — clear any previous failures
        PINService.clear_failures(user)
        logger.info("PIN login successful for %s", phone)

        return Response({
            "message": "Login successful",
            **issue_tokens(user, STAGE_ACTIVE),
        }, status=status.HTTP_200_OK)


# -----------------------------
# 5. PROTECTED TEST ROUTE
# -----------------------------
class ProtectedView(APIView):

    permission_classes = [IsActiveSession]

    def get(self, request):

        return Response({
            "message": "You are authenticated",
            "user": request.user.phone_number,
            "pin_set": request.user.is_pin_set
        })


# -----------------------------
# 6. USER PROFILE
# -----------------------------
class UserProfileView(APIView):
    permission_classes = [IsActiveSession]
    parser_classes     = [MultiPartParser, FormParser, JSONParser]

    def get(self, request):
        return Response(UserSerializer(request.user, context={'request': request}).data)

    def patch(self, request):
        """Update name, bio, and/or profile_photo."""
        serializer = UserSerializer(
            request.user,
            data=request.data,
            partial=True,
            context={'request': request},
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        serializer.save()
        return Response(serializer.data)


# -----------------------------
# 7. KYC
# -----------------------------
class KYCView(APIView):
    """
    GET  /api/users/kyc/ — return the user's KYC profile and status.
                           Returns {"status": "not_submitted"} if none exists yet.
                           Also returns county list and choice labels for the mobile form.

    POST /api/users/kyc/ — submit (or re-submit after rejection) KYC.
                           Accepts multipart/form-data so ID scan images can be uploaded.
                           Approved profiles cannot be re-submitted.
    """
    permission_classes = [IsActiveSession]
    parser_classes_override = None  # multipart handled automatically by DRF

    def get(self, request):
        try:
            kyc = request.user.kyc
            return Response(KYCStatusSerializer(kyc, context={'request': request}).data)
        except KYCProfile.DoesNotExist:
            return Response({
                'status': 'not_submitted',
                'counties':       [c[0] for c in KYCProfile.KENYA_COUNTIES],
                'income_bands':   [{'value': v, 'label': l} for v, l in KYCProfile.INCOME_BAND_CHOICES],
                'income_sources': [{'value': v, 'label': l} for v, l in KYCProfile.SOURCE_CHOICES],
            })

    def post(self, request):
        try:
            kyc = request.user.kyc
            if kyc.status == 'approved':
                return Response(
                    {'error': 'Your KYC has already been approved and cannot be re-submitted.'},
                    status=status.HTTP_409_CONFLICT,
                )
            # Re-submission after rejection — reset to pending
            serializer = KYCSubmitSerializer(kyc, data=request.data, partial=False)
        except KYCProfile.DoesNotExist:
            serializer = KYCSubmitSerializer(data=request.data)

        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        kyc = serializer.save(
            user=request.user,
            status='pending',
            rejection_reason='',
            email_verified=False,       # reset on re-submission
        )

        # NOTE: User.name (display name) is intentionally NOT synced from KYC.
        # The display name is what the user wants to appear to their community —
        # they set it themselves during onboarding and can change it any time.
        # KYC given_names + surname are the legal identity fields used only for
        # verification; they are never exposed as the profile display name.

        # Send email verification link
        _send_kyc_verification_email(kyc, request)

        return Response(
            KYCStatusSerializer(kyc, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


def _send_kyc_verification_email(kyc, request):
    """Generate a verification token and queue the email for out-of-band delivery.

    The SMTP send runs in a Celery task (apps.users.tasks) so the request returns
    immediately — sending inline previously blocked the ASGI worker until Daphne
    killed it whenever SMTP was slow.
    """
    import secrets
    from django.utils import timezone
    from .tasks import send_kyc_verification_email

    token = secrets.token_urlsafe(32)
    kyc.email_verification_token   = token
    kyc.email_verification_sent_at = timezone.now()
    kyc.email_verified             = False
    kyc.save(update_fields=['email_verification_token', 'email_verification_sent_at', 'email_verified'])

    # Build verification URL — works for both dev (console email) and production
    verify_url = request.build_absolute_uri(f"/api/users/kyc/verify-email/?token={token}")

    send_kyc_verification_email.delay(
        email=kyc.email,
        given_names=kyc.given_names,
        verify_url=verify_url,
        user_id=kyc.user_id,
    )


class KYCCheckEmailView(APIView):
    """
    GET /api/users/kyc/check-email/?email=<value>

    Soft check: is this email already used by another KYC profile?
    Returns a warning (not an error) — email is a communication channel,
    not a legally unique identifier like a national ID.

    The caller should warn the user but allow them to proceed if they
    confirm the email is theirs.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        email = request.query_params.get('email', '').strip().lower()
        if not email or '@' not in email:
            return Response({'available': True})

        taken = KYCProfile.objects.filter(
            email__iexact=email
        ).exclude(user=request.user).exists()

        if taken:
            return Response({
                'available': False,
                'warning': True,   # soft — warn, don't block
                'message': (
                    'This email is already linked to another account. '
                    'If it\'s yours, you can continue — '
                    'otherwise use a different address.'
                ),
            })
        return Response({'available': True})


class KYCEmailVerifyView(APIView):
    """
    GET /api/users/kyc/verify-email/?token=<token>

    Called when the user clicks the verification link in their email.
    No authentication required — the token IS the credential.
    Returns a simple HTML page so any browser (or email client preview) works.
    """
    permission_classes = []   # public — token is the auth

    def get(self, request):
        from django.http import HttpResponse
        from django.utils import timezone
        from datetime import timedelta

        token = request.query_params.get('token', '').strip()
        if not token:
            return HttpResponse(self._page("Invalid link", "The verification link is missing a token.", success=False))

        try:
            kyc = KYCProfile.objects.get(email_verification_token=token)
        except KYCProfile.DoesNotExist:
            return HttpResponse(self._page("Link not found", "This verification link is invalid or has already been used.", success=False))

        # Check expiry (48 hours)
        if kyc.email_verification_sent_at:
            expiry = kyc.email_verification_sent_at + timedelta(hours=48)
            if timezone.now() > expiry:
                return HttpResponse(self._page("Link expired", "This link has expired. Please re-submit your KYC to receive a new one.", success=False))

        already_verified = kyc.email_verified

        if not already_verified:
            kyc.email_verified            = True
            kyc.email_verification_token  = ''   # single-use — invalidate now
            kyc.save(update_fields=['email_verified', 'email_verification_token'])
            logger.info("KYC email verified for user %s (%s)", kyc.user_id, kyc.email)

            # ── Identity verification pipeline ────────────────────────────
            # PRODUCTION (TODO):
            #   1. Call IPRS (Integrated Population Registration System) with
            #      kyc.id_number → validates ID number is real and matches
            #      kyc.given_names / kyc.surname / kyc.date_of_birth.
            #   2. Call a selfie-vs-ID liveness API (e.g. Smile Identity,
            #      Onfido, or Jumio) with kyc.id_front and kyc.selfie.
            #   3. If ALL checks pass → approve immediately.
            #      If any check fails → set status='pending' for manual review.
            #
            # DEVELOPMENT: assume all submissions pass — auto-approve on
            # email verification so developers get full app access instantly.
            from django.conf import settings as conf
            if getattr(conf, 'DEBUG', False):
                kyc.status = 'approved'
                kyc.save(update_fields=['status'])
                logger.info(
                    "DEV auto-approve: KYC for user %s approved after email verification.",
                    kyc.user_id,
                )
                # Notify the user they are now verified
                from apps.contributions.services import _notify
                _notify(
                    user=kyc.user,
                    notification_type='join_approved',   # reuses the ✓ approved icon
                    title="Identity verified!",
                    message=(
                        "Your identity has been verified. "
                        "You now have full access to payments, contributions, and community features."
                    ),
                )
            else:
                # Production: result handled async by the ID verification webhook
                logger.info(
                    "PROD: KYC for user %s queued for identity verification pipeline.",
                    kyc.user_id,
                )

        # The email verification page ONLY confirms the email address.
        # Identity verification is a separate step — the outcome is
        # communicated via an in-app notification, not here.
        page_message = (
            f"Your email address ({kyc.email}) has been confirmed. "
            "We're now processing your identity verification in the background. "
            "Open the WEPL app — you'll receive a notification as soon as it's complete."
        )

        return HttpResponse(self._page("Email confirmed!", page_message, success=True))

    @staticmethod
    def _page(title: str, message: str, success: bool) -> str:
        colour = "#1A5C38" if success else "#C0392B"
        icon   = "✓" if success else "✗"
        return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>{title} — WEPL</title>
  <style>
    body {{ font-family: -apple-system, sans-serif; display: flex; justify-content: center;
           align-items: center; min-height: 100vh; margin: 0; background: #F5F8F6; }}
    .card {{ background: #fff; border-radius: 16px; padding: 40px 32px;
             max-width: 420px; width: 90%; text-align: center;
             box-shadow: 0 4px 24px rgba(0,0,0,.08); }}
    .icon {{ font-size: 56px; color: {colour}; margin-bottom: 16px; }}
    h1 {{ color: #111; font-size: 22px; margin: 0 0 12px; }}
    p  {{ color: #4D6358; line-height: 1.6; margin: 0 0 24px; }}
    .btn {{ display: inline-block; background: {colour}; color: #fff;
            padding: 12px 28px; border-radius: 8px; text-decoration: none;
            font-weight: 700; font-size: 15px; }}
  </style>
</head>
<body>
  <div class="card">
    <div class="icon">{icon}</div>
    <h1>{title}</h1>
    <p>{message}</p>
    <a class="btn" href="weplmobile://">Open WEPL</a>
  </div>
</body>
</html>"""


class KYCCheckIDView(APIView):
    """
    GET /api/users/kyc/check-id/?id_number=<value>

    Real-time check: is this national ID number already registered?

    Returns:
      { "available": true }   — ID is free to use
      { "available": false, "message": "..." }  — already taken

    The current user's own KYC row is excluded so re-submission after
    rejection doesn't falsely flag their own ID as taken.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        id_number = request.query_params.get('id_number', '').strip()
        if not id_number or len(id_number) < 4:
            return Response({'available': True})

        taken = KYCProfile.objects.filter(
            id_number=id_number
        ).exclude(user=request.user).exists()

        if taken:
            return Response({
                'available': False,
                'message':   'This ID number is already registered to another account.',
            })
        return Response({'available': True})


class KYCResendEmailView(APIView):
    """POST /api/users/kyc/resend-verification/ — resend the verification email."""
    permission_classes = [IsAuthenticated]

    def post(self, request):
        from django.utils import timezone
        from datetime import timedelta

        try:
            kyc = request.user.kyc
        except KYCProfile.DoesNotExist:
            return Response({'error': 'No KYC submission found.'}, status=status.HTTP_404_NOT_FOUND)

        if kyc.email_verified:
            return Response({'message': 'Email already verified.'})

        if not kyc.email:
            return Response({'error': 'No email address on file.'}, status=status.HTTP_400_BAD_REQUEST)

        # Rate-limit resend: once per 2 minutes
        if kyc.email_verification_sent_at:
            cooldown = kyc.email_verification_sent_at + timedelta(minutes=2)
            if timezone.now() < cooldown:
                wait = int((cooldown - timezone.now()).total_seconds())
                return Response(
                    {'error': f'Please wait {wait}s before requesting another email.'},
                    status=status.HTTP_429_TOO_MANY_REQUESTS,
                )

        _send_kyc_verification_email(kyc, request)
        return Response({'message': f'Verification email sent to {kyc.email}.'})


# -----------------------------
# 8. FINANCIAL SUMMARY
# -----------------------------
class FinancialSummaryView(APIView):
    """
    GET /api/users/financial-summary/

    Aggregated financial snapshot for the profile dashboard.
    Returned fields:
      total_contributed    — sum of all CONTRIBUTION transactions by this user
      total_received       — sum of all WITHDRAWAL transactions to this user
      active_contributions — count of active participations
      total_contributions  — count of all participations (ever)
      pending_advances     — count of advances in PENDING/APPROVED/DISBURSED state
      advance_balance_due  — total outstanding advance repayment balance
      this_month           — contributions made in the current calendar month
      last_month           — contributions made in the previous calendar month
      monthly_trend        — list of {month, amount} for last 6 months
      member_since         — ISO8601 date_joined
      kyc_status           — 'approved' | 'pending' | 'rejected' | 'not_submitted'
    """
    permission_classes = [IsActiveSession]

    def get(self, request):
        from django.db.models import Sum, Count, Q
        from django.db.models.functions import TruncMonth
        from django.utils import timezone
        from datetime import timedelta

        from apps.contributions.models import (
            ContributionTransaction, ContributionParticipant, EmergencyAdvance,
        )

        user = request.user
        now  = timezone.now()

        # ── Contribution sums ─────────────────────────────────────────────────
        tx_agg = ContributionTransaction.objects.filter(user=user).aggregate(
            total_contributed=Sum('amount', filter=Q(transaction_type='CONTRIBUTION')),
            total_received=Sum('amount',    filter=Q(transaction_type='WITHDRAWAL')),
            tx_count=Count('id'),
        )
        total_contributed = float(tx_agg['total_contributed'] or 0)
        total_received    = float(tx_agg['total_received']    or 0)
        tx_count          = tx_agg['tx_count'] or 0

        # ── Participation counts ──────────────────────────────────────────────
        participation = ContributionParticipant.objects.filter(user=user).aggregate(
            active_count=Count('id', filter=Q(is_active=True)),
            total_count=Count('id'),
        )
        active_contributions = participation['active_count'] or 0
        total_contributions  = participation['total_count']  or 0

        # ── Advances ─────────────────────────────────────────────────────────
        # balance_due is a @property (amount * (1 + rate/100) − repaid), not a
        # DB column — fetch the rows and sum in Python (dataset is always small).
        from decimal import Decimal as D
        active_advances = list(EmergencyAdvance.objects.filter(
            borrower=user,
            status__in=['PENDING', 'APPROVED', 'DISBURSED'],
        ).only('amount', 'interest_rate', 'amount_repaid'))
        pending_advances = len(active_advances)
        advance_balance  = float(sum(
            a.amount * (D('1') + a.interest_rate / D('100')) - a.amount_repaid
            for a in active_advances
        ))

        # ── Monthly contributions ─────────────────────────────────────────────
        month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        prev_month_start = (month_start - timedelta(days=1)).replace(
            day=1, hour=0, minute=0, second=0, microsecond=0
        )

        this_month_agg = ContributionTransaction.objects.filter(
            user=user,
            transaction_type='CONTRIBUTION',
            created_at__gte=month_start,
        ).aggregate(s=Sum('amount'))
        this_month = float(this_month_agg['s'] or 0)

        last_month_agg = ContributionTransaction.objects.filter(
            user=user,
            transaction_type='CONTRIBUTION',
            created_at__gte=prev_month_start,
            created_at__lt=month_start,
        ).aggregate(s=Sum('amount'))
        last_month = float(last_month_agg['s'] or 0)

        # ── 6-month trend ─────────────────────────────────────────────────────
        six_months_ago = month_start - timedelta(days=180)
        trend_qs = (
            ContributionTransaction.objects
            .filter(user=user, transaction_type='CONTRIBUTION', created_at__gte=six_months_ago)
            .annotate(month=TruncMonth('created_at'))
            .values('month')
            .annotate(amount=Sum('amount'))
            .order_by('month')
        )
        monthly_trend = [
            {
                'month':  entry['month'].strftime('%b %Y'),
                'amount': float(entry['amount'] or 0),
            }
            for entry in trend_qs
        ]

        # ── KYC status ───────────────────────────────────────────────────────
        try:
            kyc_status = user.kyc.status
        except Exception:
            kyc_status = 'not_submitted'

        return Response({
            'total_contributed':    total_contributed,
            'total_received':       total_received,
            'active_contributions': active_contributions,
            'total_contributions':  total_contributions,
            'pending_advances':     pending_advances,
            'advance_balance_due':  advance_balance,
            'this_month':           this_month,
            'last_month':           last_month,
            'monthly_trend':        monthly_trend,
            'tx_count':             tx_count,
            'member_since':         user.date_joined.date().isoformat(),
            'kyc_status':           kyc_status,
        })


# ─── Privacy Preferences ──────────────────────────────────────────────────────

class PrivacyPreferencesView(APIView):
    """
    GET   /api/users/privacy/  — return the user's current privacy settings
    PATCH /api/users/privacy/  — update one or more privacy settings

    Fields: phone_visibility, photo_visibility, contribution_visibility
            (each: 'everyone' | 'members' | 'nobody')
            discoverable (bool), show_online_status (bool)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
        return Response({f: getattr(prefs, f) for f in PRIVACY_FIELDS})

    def patch(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

        prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
        visibility_values = {'everyone', 'members', 'nobody'}
        bool_fields       = {'discoverable', 'show_online_status'}
        vis_fields        = {'phone_visibility', 'photo_visibility', 'contribution_visibility'}
        changed = False

        for field in PRIVACY_FIELDS:
            if field not in request.data:
                continue
            val = request.data[field]
            if field in bool_fields:
                if not isinstance(val, bool):
                    return Response(
                        {'error': f"'{field}' must be true or false."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif field in vis_fields:
                if val not in visibility_values:
                    return Response(
                        {'error': f"'{field}' must be one of: {sorted(visibility_values)}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            setattr(prefs, field, val)
            changed = True

        if changed:
            prefs.save()

        return Response({f: getattr(prefs, f) for f in PRIVACY_FIELDS})


# ─── Account Deletion ────────────────────────────────────────────────────────

class AccountDeletionView(APIView):
    """
    DELETE /api/users/account/

    Kenya Data Protection Act 2019, Section 26: right to erasure of personal data.
    Financial audit trails (ledger, transactions) are retained as required by CBK.
    PII is anonymised rather than hard-deleted.

    Blocks if:
      - User has unresolved advances (PENDING / APPROVED / DISBURSED)
      - User is the creator of a community that still has active members

    Process:
      1. Pre-condition checks
      2. Anonymise KYC: clear PII fields, delete ID scan files from storage
      3. Delete profile photo from storage
      4. Blacklist all outstanding JWT refresh tokens
      5. Anonymise User record: clear PII, disable account, invalidate credentials
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user

        # ── Pre-condition: no outstanding advances ────────────────────────────
        from apps.contributions.models import EmergencyAdvance
        active_advances = EmergencyAdvance.objects.filter(
            borrower=user,
            status__in=['PENDING', 'APPROVED', 'DISBURSED'],
        )
        if active_advances.exists():
            return Response(
                {
                    'error': (
                        'You have outstanding advance(s) that must be repaid '
                        'before your account can be deleted.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── Pre-condition: not sole creator of a community with active members ─
        from apps.communities.models import Community, CommunityMembership
        for community in Community.objects.filter(created_by=user):
            others = CommunityMembership.objects.filter(
                community=community, is_active=True
            ).exclude(user=user).count()
            if others > 0:
                return Response(
                    {
                        'error': (
                            f"You are the creator of '{community.name}' which has "
                            f"{others} active member(s). Transfer ownership or "
                            "ask all members to leave before deleting your account."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # ── Anonymise KYC profile ─────────────────────────────────────────────
        try:
            kyc = user.kyc
            for field_name in ('id_front', 'id_back'):
                file_field = getattr(kyc, field_name)
                if file_field:
                    try:
                        file_field.delete(save=False)
                    except Exception:
                        pass
            kyc.given_names    = '[deleted]'
            kyc.surname        = '[deleted]'
            kyc.id_number      = f'DELETED-{user.id}'
            kyc.email          = ''
            kyc.county         = 'Nairobi'
            kyc.occupation     = '[deleted]'
            kyc.rejection_reason = ''
            kyc.save()
        except Exception:
            pass  # no KYC profile — fine

        # ── Delete profile photo ───────────────────────────────────────────────
        if user.profile_photo:
            try:
                user.profile_photo.delete(save=False)
            except Exception:
                pass

        # ── Blacklist all outstanding JWT tokens ──────────────────────────────
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            from rest_framework_simplejwt.tokens import RefreshToken as RT
            for token in OutstandingToken.objects.filter(user=user):
                try:
                    RT(token.token).blacklist()
                except Exception:
                    pass
        except Exception:
            pass

        # ── Anonymise user record (PII scrub) ─────────────────────────────────
        user.phone_number      = f'+0000{user.id:08d}'
        user.name              = '[deleted]'
        user.bio               = ''
        user.pin               = ''
        user.is_pin_set        = False
        user.is_active         = False
        user.is_phone_verified = False
        user.profile_photo     = None
        user.save()

        logger.info("Account deletion: user %d anonymised successfully.", user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)