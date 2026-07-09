"""
Step-up (TOTP) enrolment and elevation endpoints — see ``stepup.py``, OP-3.

Every operator enrols their own authenticator (``setup`` → ``confirm``); a live
code is then exchanged at ``step-up`` for a short elevation token that unlocks
``RequireStepUp`` endpoints. Enrolment secrets and recovery codes are returned
exactly once, to the operator, over their authenticated session.
"""
from __future__ import annotations

from rest_framework import status
from rest_framework.response import Response

from .audit import record_action
from .stepup import ISSUER, STEPUP_TTL, issue_stepup_token
from .views import OpsAPIView


class TotpSetupView(OpsAPIView):
    """POST /api/ops/auth/totp/setup/ — begin (or restart) TOTP enrolment.

    Returns the provisioning URI + raw secret for the operator to scan. The
    secret is inert until ``/confirm/`` proves the authenticator is in sync."""

    def post(self, request):
        staff = request.user
        uri = staff.begin_totp_enrollment()
        record_action(action="ops.stepup.enroll_started", actor=staff, request=request)
        return Response({
            "provisioning_uri": uri,
            "secret": staff.totp_secret,
            "issuer": ISSUER,
            "account": staff.email,
        })


class TotpConfirmView(OpsAPIView):
    """POST /api/ops/auth/totp/confirm/ {code} — prove the authenticator is in
    sync. On success returns one-time recovery codes (shown once, never again)."""

    def post(self, request):
        staff = request.user
        code = (request.data.get("code") or "").strip()
        recovery = staff.confirm_totp_enrollment(code)
        if recovery is None:
            return Response(
                {"detail": "That code didn't match. Check the time on your device and try again."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        record_action(action="ops.stepup.enrolled", actor=staff, request=request)
        return Response({"recovery_codes": recovery})


class StepUpView(OpsAPIView):
    """POST /api/ops/auth/step-up/ {code} — exchange a fresh TOTP (or recovery)
    code for a short-lived elevation token, sent as ``X-Ops-StepUp`` on the
    flagged request that follows."""

    def post(self, request):
        staff = request.user
        if not staff.totp_enrolled:
            return Response(
                {"detail": "Set up an authenticator app first.", "code": "not_enrolled"},
                status=status.HTTP_409_CONFLICT,
            )
        code = (request.data.get("code") or "").strip()
        if not staff.verify_stepup(code):
            record_action(action="ops.stepup.failed", actor=staff, request=request)
            return Response({"detail": "That code isn't valid."},
                            status=status.HTTP_400_BAD_REQUEST)
        record_action(action="ops.stepup.granted", actor=staff, request=request)
        return Response({
            "token": issue_stepup_token(staff),
            "expires_in": int(STEPUP_TTL.total_seconds()),
        })
