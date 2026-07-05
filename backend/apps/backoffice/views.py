"""Back Office API (/api/ops/) — staff-authenticated operations console."""
from __future__ import annotations

from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from .audit import record_action
from .auth import StaffJWTAuthentication, issue_staff_token
from .capabilities import capabilities_for, roles_for
from .permissions import IsOperator, RequireCapability
from .search import federated_search


class OpsAPIView(APIView):
    """Base for authenticated console endpoints: staff JWT auth + operator gate.
    Ops endpoints never accept a customer token — only a StaffAccount session."""
    authentication_classes = [StaffJWTAuthentication]
    permission_classes = [IsOperator]


# ── Authentication ───────────────────────────────────────────────────────────
class StaffLoginView(APIView):
    """POST /api/ops/auth/login/ {email, password} — issue a staff session token.

    Returns ``must_change_password`` so the console can force a first-login
    password change before granting access. There is intentionally NO
    self-service password reset endpoint — resets are admin-only."""
    authentication_classes = []
    permission_classes = [AllowAny]

    def post(self, request):
        from .models import StaffAccount
        email = (request.data.get("email") or "").strip().lower()
        password = request.data.get("password") or ""
        generic = {"detail": "Invalid email or password."}

        try:
            staff = StaffAccount.objects.get(email=email)
        except StaffAccount.DoesNotExist:
            return Response(generic, status=status.HTTP_401_UNAUTHORIZED)

        if not staff.is_active or not staff.check_password(password):
            record_action(action="ops.auth.login_failed", request=request,
                          metadata={"email": email})
            return Response(generic, status=status.HTTP_401_UNAUTHORIZED)

        record_action(action="ops.auth.login", actor=staff, request=request)
        from django.utils import timezone
        staff.last_login = timezone.now()
        staff.save(update_fields=["last_login"])

        return Response({
            "token": issue_staff_token(staff),
            "must_change_password": staff.must_change_password,
            "email": staff.email,
            "name": staff.full_name,
        })


class StaffChangePasswordView(OpsAPIView):
    """POST /api/ops/auth/change-password/ {current_password, new_password} —
    operator-driven change (requires knowing the current password). Also clears
    the first-login force flag."""
    # An operator whose must_change_password is set is still authenticated, so
    # IsOperator is fine; the force is handled by the console guard + here.

    def post(self, request):
        staff = request.user
        current = request.data.get("current_password") or ""
        new = request.data.get("new_password") or ""

        if not staff.check_password(current):
            return Response({"detail": "Current password is incorrect."},
                            status=status.HTTP_400_BAD_REQUEST)
        if len(new) < 10:
            return Response({"detail": "Password must be at least 10 characters."},
                            status=status.HTTP_400_BAD_REQUEST)
        if new == current:
            return Response({"detail": "New password must differ from the current one."},
                            status=status.HTTP_400_BAD_REQUEST)

        staff.set_new_password(new)
        record_action(action="ops.auth.password_changed", actor=staff, request=request)
        return Response({"ok": True})


# ── Identity ─────────────────────────────────────────────────────────────────
class OpsMeView(OpsAPIView):
    """GET /api/ops/me/ — the operator's identity, roles and capabilities."""

    def get(self, request):
        u = request.user
        return Response({
            "id": u.id,
            "email": u.email,
            "name": u.full_name,
            "is_superuser": u.is_superuser,
            "must_change_password": u.must_change_password,
            "roles": roles_for(u),
            "capabilities": sorted(capabilities_for(u)),
        })


class OpsPingView(OpsAPIView):
    """GET /api/ops/ping/ — cheap authenticated liveness for the console shell."""

    def get(self, request):
        return Response({"ok": True})


class OpsSearchView(OpsAPIView):
    """GET /api/ops/search/?q= — federated, capability-scoped operator search."""
    permission_classes = [RequireCapability("search.global")]

    def get(self, request):
        q = request.query_params.get("q", "")
        payload = federated_search(request.user, q)
        if len(payload["query"]) >= 3 and payload["results"]:
            record_action(action="ops.search.performed", actor=request.user, request=request,
                          metadata={"query": payload["query"], "counts": payload["counts"]})
        return Response(payload)
