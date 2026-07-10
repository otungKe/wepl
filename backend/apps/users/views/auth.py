from ._common import *  # shared imports/helpers (ADR-0013 view split)

from apps.core.throttling import ResilientAnonRateThrottle


class PINLoginThrottle(ResilientAnonRateThrottle):
    """Per-IP rate limit for PIN login — uses the 'pin_login' scope from settings.
    Fails open on a cache outage (see apps.core.throttling)."""
    scope = 'pin_login'


class OTPRequestThrottle(ResilientAnonRateThrottle):
    """Per-IP rate limit for OTP requests — uses the 'otp_request' scope from settings.
    Fails open on a cache outage (see apps.core.throttling)."""
    scope = 'otp_request'


# -----------------------------
# 1. REQUEST OTP
# -----------------------------
class RequestOTPView(APIView):
    # Public endpoint — no token required.
    permission_classes = []
    throttle_classes   = [OTPRequestThrottle]

    def post(self, request):

        phone = normalize_phone(request.data.get("phone_number", ""))

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

        phone = normalize_phone(request.data.get("phone_number"))
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
            **issue_tokens(request.user, STAGE_ACTIVE, request),
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

        from apps.audit.services import AuditService
        AuditService.log("auth.pin_reset", actor=request.user, target=request.user, request=request)

        # Issue a full active session now that recovery is complete.
        return Response({
            "message": "PIN reset successfully.",
            **issue_tokens(request.user, STAGE_ACTIVE, request),
        }, status=status.HTTP_200_OK)


# -----------------------------
# 4. PIN LOGIN
# -----------------------------
class PINLoginView(APIView):
    # Public endpoint — caller is proving identity, no token exists yet.
    permission_classes = []
    throttle_classes   = [PINLoginThrottle]

    def post(self, request):

        phone = normalize_phone(request.data.get("phone_number", ""))
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
            **issue_tokens(user, STAGE_ACTIVE, request),
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
# 5b. SESSION MANAGEMENT (ADR-0010)
# -----------------------------
