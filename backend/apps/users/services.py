import logging
import secrets

from django.core.cache import cache
from django.core.exceptions import ValidationError

from apps.core.exceptions import RateLimitError, ServiceUnavailable

from .models import User
from .sms import get_sms_gateway

logger = logging.getLogger(__name__)

# OTP is *stored* in the cache (Redis), so the cache is a hard dependency for the
# OTP flow: if it is down we can neither issue nor verify a code. Convert raw
# cache-backend errors into a clean 503 (ServiceUnavailable) instead of a 500, and
# never send an SMS for a code we failed to persist. RateLimitError passes through.
_OTP_UNAVAILABLE = "Verification service is temporarily unavailable. Please try again shortly."


def _otp_cache(fn, *args, **kwargs):
    """Run a cache op for the OTP flow; a backend outage becomes a clean 503."""
    try:
        return fn(*args, **kwargs)
    except Exception as exc:  # cache/Redis unreachable
        logger.error("OTP cache backend unavailable: %s", exc)
        raise ServiceUnavailable(_OTP_UNAVAILABLE) from exc


# ─────────────────────────────────────────────────────────────
# USER SERVICE
# ─────────────────────────────────────────────────────────────

class UserService:

    @staticmethod
    def deactivate_user(user, *, reason: str = "", actor_label: str = "") -> User:
        """Platform-level deactivation (the domain's single door for it):
        blocks login, revokes every active session and outstanding refresh
        token, and audits. Community authority math already excludes
        deactivated users (Communities audit M-4)."""
        from django.utils import timezone as _tz
        from apps.audit.services import AuditService
        from . import sessions as session_registry

        if not user.is_active:
            raise ValidationError("This account is already deactivated.")
        user.is_active = False
        user.save(update_fields=["is_active"])
        revoked = session_registry.revoke_all_for_user(user)
        AuditService.log(
            "user.deactivated", target_type="user", target_id=str(user.pk),
            metadata={"reason": reason, "by": actor_label,
                      "sessions_revoked": revoked, "at": _tz.now().isoformat()},
        )
        logger.warning("User %s DEACTIVATED (%s): %s",
                       user.pk, actor_label or "system", reason or "no reason recorded")
        return user

    @staticmethod
    def reactivate_user(user, *, reason: str = "", actor_label: str = "") -> User:
        from apps.audit.services import AuditService
        if user.is_active:
            raise ValidationError("This account is already active.")
        user.is_active = True
        user.save(update_fields=["is_active"])
        AuditService.log(
            "user.reactivated", target_type="user", target_id=str(user.pk),
            metadata={"reason": reason, "by": actor_label},
        )
        logger.info("User %s reactivated (%s)", user.pk, actor_label or "system")
        return user

    @staticmethod
    def raise_verification_request(user, *, kind, title, detail, actor_label=""):
        """Raise a compliance follow-up against a user (the domain's single
        door — used by Django admin and the ops console alike). Notifies via
        the durable event bus."""
        from apps.audit.services import AuditService
        from .models import VerificationRequest

        if kind not in VerificationRequest.Kind.values:
            raise ValidationError(f"Unknown request kind: {kind!r}")
        if not title.strip() or not detail.strip():
            raise ValidationError("Both a title and details are required.")
        vreq = VerificationRequest.objects.create(
            user=user, kind=kind, title=title.strip(), detail=detail.strip(),
        )
        AuditService.log(
            "user.verification_request_raised", target_type="user",
            target_id=str(user.pk),
            metadata={"request_id": vreq.pk, "kind": kind, "title": vreq.title,
                      "by": actor_label},
        )
        from .admin import _notify_verification_request
        _notify_verification_request(vreq)
        return vreq

    @staticmethod
    def resolve_verification_request(vreq, *, note="", actor_label=""):
        """Resolve an open/submitted request with optional feedback shown to
        the user. Idempotence guard: resolving twice is refused."""
        from django.utils import timezone as _tz
        from apps.audit.services import AuditService
        from .models import VerificationRequest

        if vreq.status == VerificationRequest.Status.RESOLVED:
            raise ValidationError("This request is already resolved.")
        vreq.status = VerificationRequest.Status.RESOLVED
        vreq.review_note = note.strip()
        vreq.resolved_at = _tz.now()
        vreq.save(update_fields=["status", "review_note", "resolved_at"])
        AuditService.log(
            "user.verification_request_resolved", target_type="user",
            target_id=str(vreq.user_id),
            metadata={"request_id": vreq.pk, "note": vreq.review_note,
                      "by": actor_label},
        )
        from .admin import _notify_verification_request
        _notify_verification_request(vreq, resolved=True)
        return vreq

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
        return _otp_cache(cache.get, cls._rate_key(phone), 0) >= cls.MAX_PER_HOUR

    # ── Send ───────────────────────────────────────────────────

    @classmethod
    def send_otp(cls, phone: str) -> str:
        from django.contrib.auth.hashers import make_password

        if cls._is_rate_limited(phone):
            logger.warning("OTP rate limit exceeded for %s", phone)
            raise RateLimitError("Too many OTP requests. Please try again later.")

        # Use secrets for cryptographically secure OTP generation.
        otp = str(secrets.randbelow(900_000) + 100_000)  # 100000–999999

        # Store hashed OTP; plain text never persists. If the store is down this
        # raises ServiceUnavailable (503) BEFORE the SMS is sent — we never text a
        # code the user could not verify.
        _otp_cache(cache.set, cls._otp_key(phone), make_password(otp),
                   timeout=cls.OTP_EXPIRY_SECONDS)

        # Atomic rate-counter increment.
        # cache.add only sets the key when it does NOT exist, so two concurrent
        # callers cannot both "win" the ValueError race that the old incr+except
        # pattern had — one will add(1), the other will incr to 2.
        rate_key = cls._rate_key(phone)
        if not _otp_cache(cache.add, rate_key, 1, timeout=cls.RATE_WINDOW_SECONDS):
            _otp_cache(cache.incr, rate_key)

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
            _otp_cache(cache.delete, cls._otp_key(phone))
            return True

        verify_key = cls._verify_key(phone)
        attempts   = _otp_cache(cache.get, verify_key, 0)

        if attempts >= cls.MAX_VERIFICATION_ATTEMPTS:
            logger.warning(f"OTP verification attempts exceeded for {phone}")
            raise RateLimitError("Too many verification attempts. Please request a new OTP.")

        # The stored hash lives in the cache — a backend outage becomes a 503,
        # not a false "wrong OTP".
        cached_hash = _otp_cache(cache.get, cls._otp_key(phone))
        if not cached_hash:
            logger.info(f"No active OTP found for {phone}")
            return False

        if check_password(otp, cached_hash):
            _otp_cache(cache.delete, cls._otp_key(phone))
            _otp_cache(cache.delete, verify_key)
            logger.info(f"OTP verified for {phone}")
            return True

        # Wrong OTP — atomic failure counter increment (same add-then-incr pattern).
        if not _otp_cache(cache.add, verify_key, 1, timeout=cls.RATE_WINDOW_SECONDS):
            _otp_cache(cache.incr, verify_key)

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

    # The PIN lockout counter lives in the cache (Redis). Unlike OTP, the cache is
    # NOT a hard dependency here: the PIN itself is verified against the DB hash, so
    # these methods FAIL OPEN on a cache outage — a Redis blip must not lock every
    # member out of login (and OTP is also cache-dependent, so failing closed here
    # would make a blip a total login outage). Trade-off: brute-force lockout is
    # degraded during the outage; the login-endpoint throttle is the other guard.
    # (Flip to fail-closed here if a stricter posture is preferred.)

    @classmethod
    def is_locked(cls, user) -> bool:
        """Check if user is locked out (accepts a User instance). Fails OPEN
        (not locked) if the cache is unreachable — see class note."""
        try:
            return cache.get(cls._lock_key(user.id)) is not None
        except Exception as exc:
            logger.warning("PIN lockout check unavailable for user %s (%s) — allowing.",
                           user.id, exc)
            return False

    @classmethod
    def record_failure(cls, user):
        fail_key = cls._fail_key(user.id)
        lock_key = cls._lock_key(user.id)

        try:
            try:
                attempts = cache.incr(fail_key)
            except ValueError:
                cache.set(fail_key, 1, timeout=cls.LOCKOUT_SECONDS)
                attempts = 1

            if attempts >= cls.MAX_ATTEMPTS:
                cache.set(lock_key, True, timeout=cls.LOCKOUT_SECONDS)
                cache.delete(fail_key)
                logger.warning(f"User {user.id} locked out after {attempts} failed PIN attempts.")
        except Exception as exc:
            # Cache down — can't accrue the lockout counter. Best-effort: log and
            # continue (the failed login itself is unaffected).
            logger.warning("PIN failure not recorded for user %s (%s) — cache unavailable.",
                           user.id, exc)

    @classmethod
    def clear_failures(cls, user):
        try:
            cache.delete(cls._fail_key(user.id))
            cache.delete(cls._lock_key(user.id))
        except Exception as exc:
            logger.warning("PIN failure counters not cleared for user %s (%s).", user.id, exc)

    @staticmethod
    def set_pin(user, raw_pin: str) -> User:
        if not raw_pin.isdigit() or len(raw_pin) != 6:
            raise ValidationError("PIN must be a 6-digit number.")
        had_pin = user.is_pin_set
        user.set_pin(raw_pin)
        logger.info(f"PIN set/reset for user {user.id}")
        # Alert on a *change* (mandatory security category) — not the first-ever set.
        if had_pin:
            from apps.core.events import emit
            emit(
                "security_pin_changed",
                user_id=user.id,
                title="Your PIN was changed",
                message="Your account PIN was just changed. If this wasn't you, "
                        "contact support immediately.",
            )
        return user

    @staticmethod
    def verify_pin(user, raw_pin: str) -> bool:
        return user.check_pin(raw_pin)


class RestrictionService:
    """Domain service for account-level restrictions (Application User Management).

    The single sanctioned door for applying / lifting / querying
    ``UserRestriction`` rows. Enforcement lives at the existing chokepoints — the
    PIN-login path (LOGIN) and ``enforce_controls`` (money kinds) — which call
    the read helpers here; this service never re-implements those gates.
    """
    from .models import UserRestriction as _R

    MONEY_KINDS = frozenset({_R.Kind.PAYOUT, _R.Kind.PAYIN, _R.Kind.FREEZE})
    # Kinds that cut off access/money → sessions are killed when they land.
    SESSION_KILLING = frozenset({_R.Kind.LOGIN, _R.Kind.FREEZE})

    @classmethod
    def active(cls, user):
        """Currently-effective restrictions for a user (ACTIVE, started, unexpired)."""
        from django.db.models import Q
        from django.utils import timezone
        now = timezone.now()
        return (cls._R.objects
                .filter(user=user, status=cls._R.Status.ACTIVE, effective_at__lte=now)
                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now)))

    @classmethod
    def is_restricted(cls, user, kind) -> bool:
        return cls.active(user).filter(kind=kind).exists()

    @classmethod
    def blocks_login(cls, user) -> bool:
        return cls.is_restricted(user, cls._R.Kind.LOGIN)

    @classmethod
    def blocks_money(cls, user_id, direction):
        """Return the active restriction blocking a PAYIN/PAYOUT movement, or None.

        A FREEZE blocks both directions; PAYOUT/PAYIN block their own. Called by
        the controls chokepoint with the ledger ``LimitRule.Direction`` value.
        """
        from django.db.models import Q
        from django.utils import timezone
        kinds = [cls._R.Kind.FREEZE]
        if direction == "PAYOUT":
            kinds.append(cls._R.Kind.PAYOUT)
        elif direction == "PAYIN":
            kinds.append(cls._R.Kind.PAYIN)
        now = timezone.now()
        return (cls._R.objects
                .filter(user_id=user_id, status=cls._R.Status.ACTIVE,
                        effective_at__lte=now, kind__in=kinds)
                .filter(Q(expires_at__isnull=True) | Q(expires_at__gt=now))
                .first())

    @classmethod
    def apply(cls, user, kind, *, reason, actor_label="",
              effective_at=None, expires_at=None, approval_ref=""):
        """Place a restriction. Raises ValidationError on bad input or a duplicate
        active restriction of the same kind. Session-killing kinds revoke sessions."""
        from django.db import transaction
        from django.utils import timezone
        from apps.core.events import emit

        reason = (reason or "").strip()
        if not reason:
            raise ValidationError("A reason is required to restrict an account.")
        if kind not in cls._R.Kind.values:
            raise ValidationError(f"Unknown restriction kind: {kind!r}.")
        if expires_at is not None and expires_at <= timezone.now():
            raise ValidationError("The expiry must be in the future.")
        if cls.is_restricted(user, kind):
            raise ValidationError("An active restriction of this kind already exists.")

        with transaction.atomic():
            r = cls._R.objects.create(
                user=user, kind=kind, reason=reason,
                effective_at=effective_at or timezone.now(),
                expires_at=expires_at, applied_by_label=actor_label[:120],
                approval_ref=approval_ref[:64],
            )
            emit("account_restricted", user_id=user.id, title="Account restricted",
                 message=f"A restriction was placed on your account: {r.get_kind_display()}.")
            if kind in cls.SESSION_KILLING:
                from apps.users import sessions as session_svc
                session_svc.revoke_all_for_user(user)
        logger.info("Restriction %s applied to user %s by %s", kind, user.id, actor_label or "ops")
        return r

    @classmethod
    def lift(cls, restriction, *, actor_label="", reason=""):
        """Lift an active restriction (append-only: sets LIFTED with who/when/why)."""
        from django.db import transaction
        from django.utils import timezone
        from apps.core.events import emit

        if restriction.status != cls._R.Status.ACTIVE:
            raise ValidationError("Only an active restriction can be lifted.")
        with transaction.atomic():
            restriction.status = cls._R.Status.LIFTED
            restriction.lifted_at = timezone.now()
            restriction.lifted_by_label = actor_label[:120]
            restriction.lift_reason = (reason or "").strip()
            restriction.save(update_fields=["status", "lifted_at", "lifted_by_label", "lift_reason"])
            emit("account_restriction_lifted", user_id=restriction.user_id,
                 title="Restriction lifted",
                 message=f"A restriction on your account was lifted: {restriction.get_kind_display()}.")
        logger.info("Restriction %s lifted for user %s by %s",
                    restriction.kind, restriction.user_id, actor_label or "ops")
        return restriction

    @classmethod
    def expire_due(cls) -> int:
        """Sweep ACTIVE restrictions past their expiry → EXPIRED. Reads already
        treat them as inactive; this is housekeeping + a clean state signal."""
        from django.utils import timezone
        return (cls._R.objects
                .filter(status=cls._R.Status.ACTIVE, expires_at__isnull=False,
                        expires_at__lte=timezone.now())
                .update(status=cls._R.Status.EXPIRED))

    @classmethod
    def account_status(cls, user) -> str:
        """Derived lifecycle status for the ops directory / profile.

        Precedence: closed (account deactivated) > suspended (login or full
        freeze) > restricted (any other active restriction) > dormant (no login
        in 90 days) > active. Not stored — always computed from the source data.
        """
        from django.utils import timezone
        if not user.is_active:
            return "closed"
        kinds = set(cls.active(user).values_list("kind", flat=True))
        if cls._R.Kind.LOGIN in kinds or cls._R.Kind.FREEZE in kinds:
            return "suspended"
        if kinds:
            return "restricted"
        if user.last_seen and (timezone.now() - user.last_seen).days >= 90:
            return "dormant"
        return "active"
