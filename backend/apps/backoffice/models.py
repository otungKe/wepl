"""
Staff identity for the Back Office (operations console).

Operators are a *separate* identity from customers: they authenticate with a
corporate email + password, never a phone/OTP, and their account lifecycle
(provisioning, password reset) is controlled by a Platform Super Admin — an
operator cannot self-serve a reset. See ADR (Back Office v2).

``StaffAccount`` is an ``AbstractBaseUser`` (for password hashing + last_login)
but is *not* the project's ``AUTH_USER_MODEL`` — it is an independent identity
store. Roles are the ``ops:*`` Django Groups; the capability map in
``capabilities.py`` resolves them the same way for staff as it did for the
earlier prototype.
"""
from __future__ import annotations

import secrets

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.contrib.auth.models import Group
from django.db import models
from django.utils import timezone


class StaffAccountManager(BaseUserManager):
    use_in_migrations = True

    def _normalise(self, email: str) -> str:
        return self.normalize_email((email or "").strip().lower())

    def create_staff(self, email, *, full_name="", password=None,
                     is_superuser=False, must_change_password=True, roles=None):
        if not email:
            raise ValueError("Staff accounts require an email address.")
        acct = self.model(
            email=self._normalise(email),
            full_name=full_name.strip(),
            is_superuser=is_superuser,
            must_change_password=must_change_password,
        )
        if password:
            acct.set_password(password)
        else:
            acct.set_unusable_password()
        acct.save(using=self._db)
        for role in (roles or []):
            g, _ = Group.objects.get_or_create(name=role)
            acct.groups.add(g)
        return acct

    def get_by_natural_key(self, email):
        return self.get(email=self._normalise(email))


class StaffAccount(AbstractBaseUser):
    """A Back Office operator. Corporate email + password; admin-managed."""

    email      = models.EmailField(unique=True)
    full_name  = models.CharField(max_length=120, blank=True, default="")
    is_active  = models.BooleanField(default=True)
    # Platform Super Admin — implicitly holds every capability (break-glass).
    is_superuser = models.BooleanField(default=False)

    # Operational roles (ops:* Django Groups). The capability layer reads these.
    groups = models.ManyToManyField(Group, blank=True, related_name="staff_accounts")

    # Lifecycle — provisioning & reset are controlled by an admin, not the user.
    must_change_password = models.BooleanField(
        default=True,
        help_text="Forces the operator to set their own password before using the console.",
    )
    password_changed_at = models.DateTimeField(null=True, blank=True)
    created_by = models.CharField(max_length=120, blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    # Step-up (TOTP) — a fresh code grants a short elevated window for destructive
    # levers. See stepup.py and the Production Operations Roadmap (OP-3). The
    # secret sits in the same trust boundary as the password hash; encrypting it
    # at rest is a noted hardening follow-up.
    totp_secret = models.CharField(max_length=64, blank=True, default="")
    totp_confirmed_at = models.DateTimeField(null=True, blank=True)
    totp_recovery_codes = models.JSONField(default=list, blank=True)

    objects = StaffAccountManager()

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS: list[str] = []

    class Meta:
        verbose_name = "staff account"
        ordering = ["email"]

    def __str__(self):
        return self.email

    # ── Capability-layer duck-typing (mirrors the ops permission checks) ──────
    @property
    def is_staff(self) -> bool:
        """Every StaffAccount is, by definition, staff. Kept so the Django admin
        and capability helpers can treat it uniformly."""
        return True

    def set_new_password(self, raw_password: str):
        """Operator-driven change: sets the password and clears the force flag."""
        self.set_password(raw_password)
        self.must_change_password = False
        self.password_changed_at = timezone.now()
        self.save(update_fields=["password", "must_change_password", "password_changed_at"])

    def force_reset(self) -> str:
        """Admin-driven reset: issue a one-time temp password and require a change
        on next login. Returns the temp password (shown once to the admin)."""
        temp = secrets.token_urlsafe(9)
        self.set_password(temp)
        self.must_change_password = True
        self.password_changed_at = None
        self.save(update_fields=["password", "must_change_password", "password_changed_at"])
        return temp

    # ── Step-up (TOTP) enrolment & verification ──────────────────────────────
    @property
    def totp_enrolled(self) -> bool:
        return self.totp_confirmed_at is not None

    def begin_totp_enrollment(self) -> str:
        """Generate a fresh (unconfirmed) secret and return its provisioning URI.
        Re-enrolling replaces any prior secret, but only takes effect on confirm."""
        from . import stepup
        self.totp_secret = stepup.generate_secret()
        self.totp_confirmed_at = None
        self.save(update_fields=["totp_secret", "totp_confirmed_at", "updated_at"])
        return stepup.provisioning_uri(self.totp_secret, self.email)

    def confirm_totp_enrollment(self, code: str) -> list[str] | None:
        """Verify the first code against the pending secret. On success, mark
        enrolled and return one-time recovery codes (shown once); else ``None``."""
        from . import stepup
        if not self.totp_secret or not stepup.verify_code(self.totp_secret, code):
            return None
        plain, hashed = stepup.generate_recovery_codes()
        self.totp_recovery_codes = hashed
        self.totp_confirmed_at = timezone.now()
        self.save(update_fields=["totp_recovery_codes", "totp_confirmed_at", "updated_at"])
        return plain

    def verify_stepup(self, code: str) -> bool:
        """Accept a current TOTP code, or consume a single-use recovery code."""
        from . import stepup
        if not self.totp_enrolled:
            return False
        if stepup.verify_code(self.totp_secret, code):
            return True
        remaining = stepup.consume_recovery_code(self.totp_recovery_codes, code)
        if remaining is not None:
            self.totp_recovery_codes = remaining
            self.save(update_fields=["totp_recovery_codes", "updated_at"])
            return True
        return False
