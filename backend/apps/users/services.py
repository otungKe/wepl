import logging
import secrets

from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.core.exceptions import RateLimitError

from .models import User
from .sms import get_sms_gateway

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────
# USER SERVICE
# ─────────────────────────────────────────────────────────────

class UserService:

    @staticmethod
    def get_or_create_user(phone_number: str) -> User:
        """Retrieve existing user or create a new one."""
        user, _ = User.objects.get_or_create(phone_number=phone_number)
        logger.info(f"User retrieved/created with phone {phone_number} (id: {user.id})")
        return user

    @staticmethod
    def update_profile(user, validated_data: dict) -> User:
        """Update editable profile fields (name, bio, profile_photo)."""
        updated_fields = []
        for field in ('name', 'bio', 'profile_photo'):
            if field in validated_data:
                setattr(user, field, validated_data[field])
                updated_fields.append(field)
        if updated_fields:
            user.save(update_fields=updated_fields)
            logger.info(f"Profile updated for user {user.id}: {updated_fields}")
        return user


# ─────────────────────────────────────────────────────────────
# OTP SERVICE
# ─────────────────────────────────────────────────────────────

class OTPService:

    OTP_EXPIRY_SECONDS       = 300   # 5 minutes
    MAX_PER_HOUR             = 3
    RATE_WINDOW_SECONDS      = 3600  # 1 hour
    MAX_VERIFICATION_ATTEMPTS = 5

    # ── Cache key helpers ──────────────────────────────────────

    @staticmethod
    def _rate_key(phone: str) -> str:
        return f"otp_rate_{phone}"

    @staticmethod
    def _otp_key(phone: str) -> str:
        return f"otp_{phone}"

    @staticmethod
    def _verify_key(phone: str) -> str:
        return f"otp_verify_{phone}"

    # ── Rate limit ─────────────────────────────────────────────

    @classmethod
    def _is_rate_limited(cls, phone: str) -> bool:
        """Returns True when the phone has exceeded MAX_PER_HOUR requests."""
        return cache.get(cls._rate_key(phone), 0) >= cls.MAX_PER_HOUR

    # ── Send ───────────────────────────────────────────────────

    @classmethod
    def send_otp(cls, phone: str) -> str:
        from django.contrib.auth.hashers import make_password

        if cls._is_rate_limited(phone):
            logger.warning("OTP rate limit exceeded for %s", phone)
            raise RateLimitError("Too many OTP requests. Please try again later.")

        # Use secrets for cryptographically secure OTP generation.
        otp = str(secrets.randbelow(900_000) + 100_000)  # 100000–999999

        # Store hashed OTP; plain text never persists.
        cache.set(cls._otp_key(phone), make_password(otp), timeout=cls.OTP_EXPIRY_SECONDS)

        # Atomic rate-counter increment.
        # cache.add only sets the key when it does NOT exist, so two concurrent
        # callers cannot both "win" the ValueError race that the old incr+except
        # pattern had — one will add(1), the other will incr to 2.
        rate_key = cls._rate_key(phone)
        if not cache.add(rate_key, 1, timeout=cls.RATE_WINDOW_SECONDS):
            cache.incr(rate_key)

        message = f"Your WEPL OTP is {otp}. It expires in 5 minutes. Do not share it."

        from django.conf import settings
        if getattr(settings, 'STAGING_OTP_BYPASS', False):
            logger.info("[STAGING] OTP for %s is %s (SMS not sent)", phone, otp)
        else:
            try:
                get_sms_gateway().send(message, phone)
                logger.info("OTP SMS sent to %s", phone)
            except Exception as exc:
                logger.error("Failed to send OTP SMS to %s: %s", phone, exc)
                raise RuntimeError("Failed to send OTP. Please try again.") from exc

        return otp

    # ── Verify ─────────────────────────────────────────────────

    @classmethod
    def verify_otp(cls, phone: str, otp: str) -> bool:
        from django.contrib.auth.hashers import check_password
        from django.conf import settings

        # Staging bypass: fixed OTP for testing — never active in production.
        if getattr(settings, 'STAGING_OTP_BYPASS', False) and otp == '000000':
            logger.info("Staging OTP bypass used for %s", phone)
            cache.delete(cls._otp_key(phone))
            return True

        verify_key = cls._verify_key(phone)
        attempts   = cache.get(verify_key, 0)

        if attempts >= cls.MAX_VERIFICATION_ATTEMPTS:
            logger.warning(f"OTP verification attempts exceeded for {phone}")
            raise RateLimitError("Too many verification attempts. Please request a new OTP.")

        cached_hash = cache.get(cls._otp_key(phone))
        if not cached_hash:
            logger.info(f"No active OTP found for {phone}")
            return False

        if check_password(otp, cached_hash):
            cache.delete(cls._otp_key(phone))
            cache.delete(verify_key)
            logger.info(f"OTP verified for {phone}")
            return True

        # Wrong OTP — atomic failure counter increment (same add-then-incr pattern).
        if not cache.add(verify_key, 1, timeout=cls.RATE_WINDOW_SECONDS):
            cache.incr(verify_key)

        logger.info("OTP mismatch for %s (attempt %d)", phone, attempts + 1)
        return False


# ─────────────────────────────────────────────────────────────
# PIN SERVICE
# ─────────────────────────────────────────────────────────────

class PINService:
    """Named PINService (uppercase N) to match views.py imports."""

    MAX_ATTEMPTS    = 5
    LOCKOUT_SECONDS = 1800  # 30 minutes

    @staticmethod
    def _fail_key(user_id: int) -> str:
        return f"pin_fail_{user_id}"

    @staticmethod
    def _lock_key(user_id: int) -> str:
        return f"pin_lock_{user_id}"

    @classmethod
    def is_locked(cls, user) -> bool:
        """Check if user is locked out (accepts a User instance)."""
        return cache.get(cls._lock_key(user.id)) is not None

    @classmethod
    def record_failure(cls, user):
        fail_key = cls._fail_key(user.id)
        lock_key = cls._lock_key(user.id)

        try:
            attempts = cache.incr(fail_key)
        except ValueError:
            cache.set(fail_key, 1, timeout=cls.LOCKOUT_SECONDS)
            attempts = 1

        if attempts >= cls.MAX_ATTEMPTS:
            cache.set(lock_key, True, timeout=cls.LOCKOUT_SECONDS)
            cache.delete(fail_key)
            logger.warning(f"User {user.id} locked out after {attempts} failed PIN attempts.")

    @classmethod
    def clear_failures(cls, user):
        cache.delete(cls._fail_key(user.id))
        cache.delete(cls._lock_key(user.id))

    @staticmethod
    def set_pin(user, raw_pin: str) -> User:
        if not raw_pin.isdigit() or len(raw_pin) != 6:
            raise ValidationError("PIN must be a 6-digit number.")
        user.set_pin(raw_pin)
        logger.info(f"PIN set/reset for user {user.id}")
        return user

    @staticmethod
    def verify_pin(user, raw_pin: str) -> bool:
        return user.check_pin(raw_pin)
