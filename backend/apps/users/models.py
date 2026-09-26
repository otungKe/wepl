import secrets

from django.conf import settings
from django.contrib.auth.models import AbstractUser, BaseUserManager
from django.core.exceptions import ValidationError
from django.db import models
from django.contrib.auth.hashers import make_password, check_password
from django.utils import timezone

# Unambiguous base32 (no 0/1/I/L/O/U) — member numbers get read aloud on support
# calls, so avoid characters people confuse.
_MEMBER_NO_ALPHABET = "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def generate_member_number() -> str:
    """An opaque, non-PII member handle, e.g. ``WM-7F9K2``."""
    return "WM-" + "".join(secrets.choice(_MEMBER_NO_ALPHABET) for _ in range(5))


# ─────────────────────────────────────────────────────────────
# CUSTOM USER MANAGER
# ─────────────────────────────────────────────────────────────

class UserManager(BaseUserManager):
    def create_user(self, phone_number, password=None, **extra_fields):
        if not phone_number:
            raise ValueError('Phone number must be provided')
        user = self.model(phone_number=phone_number, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, phone_number, password=None, **extra_fields):
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        return self.create_user(phone_number, password, **extra_fields)


# ─────────────────────────────────────────────────────────────
# USER MODEL
# ─────────────────────────────────────────────────────────────

class User(AbstractUser):
    username = None  # removed — phone_number is the unique identifier
    phone_number = models.CharField(max_length=15, unique=True)
    name         = models.CharField(max_length=120, blank=True, default="")
    pin          = models.CharField(max_length=128, blank=True, default="")

    is_phone_verified = models.BooleanField(default=False)
    is_pin_set        = models.BooleanField(default=False)
    last_seen         = models.DateTimeField(null=True, blank=True, db_index=True)

    profile_photo = models.ImageField(upload_to='profile/', blank=True, null=True)
    bio           = models.TextField(blank=True, default="")

    # Stable, non-PII member handle (e.g. WM-7F9K2). Shareable in support without
    # saying the phone aloud, survives a phone-number change, searchable in ops.
    # Phone number remains the authentication identifier.
    member_number = models.CharField(
        max_length=16, unique=True, null=True, blank=True, db_index=True)

    USERNAME_FIELD  = 'phone_number'
    REQUIRED_FIELDS = []

    objects = UserManager()

    def save(self, *args, **kwargs):
        if not self.member_number:
            self.member_number = self._unique_member_number()
        super().save(*args, **kwargs)

    @classmethod
    def _unique_member_number(cls) -> str:
        for _ in range(12):
            candidate = generate_member_number()
            if not cls.objects.filter(member_number=candidate).exists():
                return candidate
        # Astronomically unlikely — widen to remove any doubt.
        return "WM-" + "".join(secrets.choice(_MEMBER_NO_ALPHABET) for _ in range(9))

    def set_pin(self, raw_pin: str):
        if not raw_pin.isdigit() or len(raw_pin) != 6:
            raise ValidationError("PIN must be a 6-digit number.")
        self.pin       = make_password(raw_pin)
        self.is_pin_set = True
        self.save(update_fields=['pin', 'is_pin_set'])

    def check_pin(self, raw_pin: str) -> bool:
        if not self.pin:
            return False
        return check_password(raw_pin, self.pin)

    # ── Access tiers (ADR-0022) ──────────────────────────────────────────────
    # Derived from verification state — nothing extra is stored.
    #   Tier 0: identity verified (phone), KYC not yet approved  → discovery only
    #   Tier 1: identity verified + KYC approved                 → full access
    @property
    def kyc_status(self) -> str:
        """'not_submitted' | 'pending' | 'approved' | 'rejected' — safe if no KYC."""
        try:
            return self.kyc.status
        except self.__class__.kyc.RelatedObjectDoesNotExist:
            return 'not_submitted'

    @property
    def is_tier1(self) -> bool:
        """Full access: phone verified AND KYC approved (pending/rejected do not qualify)."""
        return bool(self.is_phone_verified) and self.kyc_status == 'approved'

    @property
    def is_tier0(self) -> bool:
        """Verified identity, not yet KYC-approved."""
        return not self.is_tier1

    def has_full_access(self) -> bool:
        return self.is_tier1

    def __str__(self):
        return f"{self.name} ({self.phone_number})"


# ─────────────────────────────────────────────────────────────
# PRIVACY PREFERENCES
# ─────────────────────────────────────────────────────────────

class PrivacyPreferences(models.Model):
    """
    Per-user privacy settings.

    One row per user, auto-created on first access with sensible defaults.
    Enforced in serializers and service-layer lookups — not just stored client-side.
    """

    VISIBILITY_CHOICES = [
        ('everyone', 'Everyone'),
        ('members',  'My communities only'),
        ('nobody',   'Only me'),
    ]

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name='privacy_prefs',
    )

    # Profile visibility
    phone_visibility        = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='members')
    photo_visibility        = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='everyone')
    # Financial
    contribution_visibility = models.CharField(max_length=10, choices=VISIBILITY_CHOICES, default='members')
    # Discovery
    discoverable            = models.BooleanField(default=True)
    # Chat
    show_online_status      = models.BooleanField(default=True)

    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Privacy({self.user.phone_number})"


# ─────────────────────────────────────────────────────────────
# USER SESSION (device/session registry — ADR-0010)
# ─────────────────────────────────────────────────────────────

class UserSession(models.Model):
    """One row per active login, keyed by a ``sid`` UUID embedded in the JWT.

    The ``sid`` survives refresh-token rotation (SimpleJWT copies non-reserved
    claims), so a single row represents the whole rotation chain of one login.
    Setting ``revoked_at`` kills the session: both the authentication class and
    the refresh view reject any token whose ``sid`` points here.
    """
    import uuid as _uuid

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="sessions",
    )
    sid = models.UUIDField(default=_uuid.uuid4, editable=False, unique=True, db_index=True)

    device_label = models.CharField(max_length=120, blank=True, default="")
    user_agent   = models.CharField(max_length=400, blank=True, default="")
    ip_address   = models.GenericIPAddressField(null=True, blank=True)

    created_at   = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(auto_now_add=True)
    revoked_at   = models.DateTimeField(null=True, blank=True)

    class Meta:
        indexes = [
            models.Index(fields=["user", "revoked_at"], name="usersession_user_active_idx"),
        ]
        ordering = ["-last_seen_at"]

    def __str__(self):
        state = "revoked" if self.revoked_at else "active"
        return f"Session({self.user_id}, {self.device_label or 'device'}, {state})"

    @property
    def is_active(self) -> bool:
        return self.revoked_at is None
