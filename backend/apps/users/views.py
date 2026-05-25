from django.contrib.auth import get_user_model

from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.throttling import AnonRateThrottle

from rest_framework_simplejwt.tokens import RefreshToken

from .models import KYCProfile
from .serializers import KYCSubmitSerializer, KYCStatusSerializer
from .services import UserService, OTPService, PINService


class PINLoginThrottle(AnonRateThrottle):
    """Per-IP rate limit for PIN login — uses the 'pin_login' scope from settings."""
    scope = 'pin_login'


class OTPRequestThrottle(AnonRateThrottle):
    """Per-IP rate limit for OTP requests — uses the 'otp_request' scope from settings."""
    scope = 'otp_request'

User = get_user_model()


# -----------------------------
# 1. REQUEST OTP
# -----------------------------
class RequestOTPView(APIView):
    throttle_classes = [OTPRequestThrottle]

    def post(self, request):

        phone = request.data.get("phone_number", "").strip()

        if not phone:
            return Response(
                {"error": "phone_number is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Tell the frontend whether this phone already has a registered account
        # so it can show the right UI (login hint vs. registration flow).
        # OTP is sent either way — it's also the PIN-recovery path.
        is_registered = User.objects.filter(
            phone_number=phone, is_pin_set=True
        ).exists()

        OTPService.send_otp(phone)

        return Response({
            "message": "OTP sent.",
            "is_registered": is_registered,
        }, status=status.HTTP_200_OK)


# -----------------------------
# 2. VERIFY OTP → TEMP JWT
# -----------------------------
class VerifyOTPView(APIView):

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

        refresh = RefreshToken.for_user(user)

        if user.is_pin_set:
            # Fully-registered user — OTP used as PIN-recovery path.
            # Issue a *recovery* token, not a full session.
            # The frontend should direct them to /pin/reset/ not /pin/set/.
            refresh["stage"] = "otp_recovery"
            return Response({
                "message": "OTP verified.",
                "access":       str(refresh.access_token),
                "refresh":      str(refresh),
                "is_new_user":  False,
                "next_step":    "reset_pin",
            }, status=status.HTTP_200_OK)
        else:
            # New user or incomplete onboarding (OTP verified, PIN not yet set).
            refresh["stage"] = "otp_verified"
            return Response({
                "message":      "OTP verified.",
                "access":       str(refresh.access_token),
                "refresh":      str(refresh),
                "is_new_user":  True,
                "next_step":    "set_pin",
            }, status=status.HTTP_200_OK)


# -----------------------------
# 3. SET PIN (NEW USERS ONLY)
# -----------------------------
class SetPINView(APIView):
    """
    First-time PIN setup for new / not-yet-onboarded users.

    Blocked for users who already have a PIN — they must use
    /auth/pin/reset/ (which requires a fresh OTP verification).
    """

    permission_classes = [IsAuthenticated]

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

        refresh = RefreshToken.for_user(request.user)
        refresh["stage"] = "active"

        return Response({
            "message": "PIN set successfully.",
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
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

    permission_classes = [IsAuthenticated]

    def post(self, request):

        # Enforce that this token came from the OTP recovery flow.
        stage = request.auth.payload.get("stage") if request.auth else None
        if stage != "otp_recovery":
            return Response(
                {"error": "PIN reset requires a fresh OTP verification first."},
                status=status.HTTP_403_FORBIDDEN
            )

        pin = request.data.get("pin")

        if not pin:
            return Response(
                {"error": "PIN is required"},
                status=status.HTTP_400_BAD_REQUEST
            )

        PINService.set_pin(request.user, pin)

        # Issue a full active session now that recovery is complete.
        refresh = RefreshToken.for_user(request.user)
        refresh["stage"] = "active"

        return Response({
            "message": "PIN reset successfully.",
            "access":  str(refresh.access_token),
            "refresh": str(refresh),
        }, status=status.HTTP_200_OK)


# -----------------------------
# 4. PIN LOGIN
# -----------------------------
class PINLoginView(APIView):
    throttle_classes = [PINLoginThrottle]

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
            return Response(
                {"error": "Invalid phone number or PIN."},
                status=status.HTTP_401_UNAUTHORIZED
            )

        # Successful login — clear any previous failures
        PINService.clear_failures(user)

        refresh = RefreshToken.for_user(user)
        refresh["stage"] = "active"

        return Response({
            "message": "Login successful",
            "access": str(refresh.access_token),
            "refresh": str(refresh)
        }, status=status.HTTP_200_OK)


# -----------------------------
# 5. PROTECTED TEST ROUTE
# -----------------------------
class ProtectedView(APIView):

    permission_classes = [IsAuthenticated]

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

    permission_classes = [IsAuthenticated]

    def get(self, request):

        return Response({
            "id": request.user.id,
            "phone_number": request.user.phone_number,
            "name": request.user.name,
            "bio": request.user.bio,
            "is_pin_set": request.user.is_pin_set,
        })

    def patch(self, request):

        bio = request.data.get("bio")
        name = request.data.get("name")

        updated_fields = []

        if bio is not None:
            request.user.bio = bio
            updated_fields.append("bio")

        if name is not None:
            request.user.name = name
            updated_fields.append("name")

        if updated_fields:
            request.user.save(update_fields=updated_fields)

        return Response({
            "id": request.user.id,
            "phone_number": request.user.phone_number,
            "name": request.user.name,
            "bio": request.user.bio,
        })


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
    permission_classes = [IsAuthenticated]
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

        kyc = serializer.save(user=request.user, status='pending', rejection_reason='')

        # Sync display name on the User record from the canonical KYC fields
        full = f"{kyc.given_names} {kyc.surname}".strip()
        if full:
            request.user.name = full
            request.user.save(update_fields=['name'])

        return Response(
            KYCStatusSerializer(kyc, context={'request': request}).data,
            status=status.HTTP_201_CREATED,
        )


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
    permission_classes = [IsAuthenticated]

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