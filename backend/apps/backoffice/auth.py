"""
Staff authentication for the Back Office — a self-contained JWT flow, separate
from the customer SimpleJWT/OTP path. Tokens are signed with the project
SECRET_KEY and carry ``type: "ops"`` so a customer token can never authenticate
against the console and vice-versa.
"""
from __future__ import annotations

from datetime import timedelta

import jwt
from django.conf import settings
from django.utils import timezone
from rest_framework import authentication, exceptions

STAFF_TOKEN_TYPE = "ops"
STAFF_TOKEN_TTL = timedelta(hours=12)   # one shift; operator re-logs in daily


def issue_staff_token(staff) -> str:
    now = timezone.now()
    payload = {
        "type": STAFF_TOKEN_TYPE,
        "sid": staff.id,
        "email": staff.email,
        "iat": int(now.timestamp()),
        "exp": int((now + STAFF_TOKEN_TTL).timestamp()),
    }
    return jwt.encode(payload, settings.SECRET_KEY, algorithm="HS256")


class StaffJWTAuthentication(authentication.BaseAuthentication):
    """Authenticates ops requests as a ``StaffAccount`` from a staff JWT."""

    keyword = "Bearer"

    def authenticate(self, request):
        header = authentication.get_authorization_header(request).decode("utf-8")
        if not header.startswith(self.keyword + " "):
            return None
        token = header[len(self.keyword) + 1:].strip()
        try:
            payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
        except jwt.ExpiredSignatureError:
            raise exceptions.AuthenticationFailed("Session expired — please sign in again.")
        except jwt.InvalidTokenError:
            return None  # not a staff token; let other authenticators try / fall to 401

        if payload.get("type") != STAFF_TOKEN_TYPE:
            return None

        from .models import StaffAccount
        try:
            staff = StaffAccount.objects.get(id=payload.get("sid"), is_active=True)
        except StaffAccount.DoesNotExist:
            raise exceptions.AuthenticationFailed("Staff account not found or disabled.")
        return (staff, token)

    def authenticate_header(self, request):
        # Makes DRF return 401 (not 403) when credentials are missing/invalid.
        return self.keyword
