import logging
import random

import africastalking
from django.conf import settings
from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.core.exceptions import RateLimitError

from .models import User

logger = logging.getLogger(__name__)

# Initialise Africa's Talking once at import time (safe — settings are frozen by then)
africastalking.initialize(
    settings.AT_USERNAME,
    settings.AT_API_KEY,
)
_at_sms = africastalking.SMS


# ─────────────────────────────────────────────────────────────────────────────
# USER SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class UserService:

    @staticmethod
    def get_or_create_user(phone_number):
        user, _ = User.objects.get_or_create(phone_number=phone_number)
        return user

    @staticmethod
    def update_profile(user, data):
        user.bio = data.get("bio", user.bio)
        user.profile_photo = data.get("profile_photo", user.profile_photo)
        user.save()
        return user


# ─────────────────────────────────────────────────────────────────────────────
# OTP SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class OTPService:

    OTP_EXPIRY     = 600   # 10 minutes
    MAX_PER_HOUR   = 3     # max OTP requests per phone per hour
    RATE_WINDOW    = 3600  # 1 hour window for the counter

    @staticmethod
    def _rate_key(phone_number: str) -> str:
        return f"otp_rate_{phone_number}"

    @staticmethod
    def _otp_key(phone_number: str) -> str:
        return f"otp_{phone_number}"

    @classmethod
    def check_rate_limit(cls, phone_number: str) -> bool:
        """Return True if the phone is allowed to request another OTP."""
        key = cls._rate_key(phone_number)
        count = cache.get(key, 0)
        return count < cls.MAX_PER_HOUR

    @classmethod
    def send_otp(cls, phone_number: str) -> str:
        if not cls.check_rate_limit(phone_number):
            raise RateLimitError("Too many OTP requests. Please wait an hour before trying again.")

        otp = str(random.randint(100000, 999999))
        cache.set(cls._otp_key(phone_number), otp, timeout=cls.OTP_EXPIRY)

        # Increment rate-limit counter
        rate_key = cls._rate_key(phone_number)
        try:
            cache.incr(rate_key)
        except ValueError:
            # Key doesn't exist yet
            cache.set(rate_key, 1, timeout=cls.RATE_WINDOW)

        # Send OTP via Africa's Talking SMS
        message = f"Your WEPL verification code is {otp}. Valid for 10 minutes. Do not share it."
        try:
            sender = getattr(settings, 'AT_SENDER_ID', None) or None
            _at_sms.send(message, [phone_number], sender_id=sender)
            logger.info("OTP SMS sent to %s", phone_number)
        except Exception as exc:
            logger.error("AT SMS delivery failed for %s: %s", phone_number, exc)
            if settings.DEBUG:
                # In development, print to console so testing still works
                # even if the SMS key is misconfigured.
                print(f"\n[DEV OTP] {phone_number} → {otp}\n")
            else:
                raise RuntimeError("Could not send verification SMS. Please try again.") from exc

        return otp

    @classmethod
    def verify_otp(cls, phone_number: str, otp: str) -> bool:
        stored = cache.get(cls._otp_key(phone_number))
        if stored and stored == otp:
            cache.delete(cls._otp_key(phone_number))
            return True
        return False


# ─────────────────────────────────────────────────────────────────────────────
# PIN SERVICE
# ─────────────────────────────────────────────────────────────────────────────

class PINService:

    MAX_ATTEMPTS   = 5    # failed attempts before lockout
    LOCKOUT_SECONDS = 1800  # 30 minutes

    @staticmethod
    def _fail_key(user_id: int) -> str:
        return f"pin_fail_{user_id}"

    @staticmethod
    def _lock_key(user_id: int) -> str:
        return f"pin_lock_{user_id}"

    @classmethod
    def is_locked(cls, user) -> bool:
        return bool(cache.get(cls._lock_key(user.id)))

    @classmethod
    def record_failure(cls, user):
        fail_key = cls._fail_key(user.id)
        try:
            attempts = cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, timeout=cls.LOCKOUT_SECONDS)
            attempts = 1

        if attempts >= cls.MAX_ATTEMPTS:
            cache.set(cls._lock_key(user.id), True, timeout=cls.LOCKOUT_SECONDS)
            cache.delete(fail_key)

    @classmethod
    def clear_failures(cls, user):
        cache.delete(cls._fail_key(user.id))
        cache.delete(cls._lock_key(user.id))

    @staticmethod
    def set_pin(user, pin: str):
        if len(pin) != 6 or not pin.isdigit():
            raise ValidationError("PIN must be 6 digits")
        # user.set_pin() hashes the PIN, sets is_pin_set=True, and saves — no second save needed.
        user.set_pin(pin)
        return user

    @staticmethod
    def verify_pin(user, pin: str) -> bool:
        return user.check_pin(pin)