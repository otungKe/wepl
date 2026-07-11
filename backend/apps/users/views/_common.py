import logging

from django.contrib.auth import get_user_model

from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser, JSONParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle
from rest_framework.views import APIView

from ..auth import (
    STAGE_ACTIVE, STAGE_OTP_RECOVERY, STAGE_OTP_VERIFIED,
    IsActiveSession, StageRequired, issue_tokens,
)
from ..models import KYCProfile, PrivacyPreferences
from ..phone import normalize_phone
from ..serializers import UserSerializer, KYCSubmitSerializer, KYCStatusSerializer
from ..services import UserService, OTPService, PINService

PRIVACY_FIELDS = (
    'phone_visibility', 'photo_visibility', 'contribution_visibility',
    'discoverable', 'show_online_status',
)

logger = logging.getLogger(__name__)

User = get_user_model()

# Export top-level names so each view sub-module gets the shared imports
# via `from ._common import *` (ADR-0013).
__all__ = [n for n in dir() if not n.startswith('__')]
