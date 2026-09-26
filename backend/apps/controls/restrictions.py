"""Account restrictions: the rows, and the one door that applies and lifts them.

A restriction is a control, so it lives with the controls it feeds: the money
kinds are enforced by ``enforce_controls`` at the posting chokepoint in this app,
and ``LOGIN`` by the PIN-login path, which asks ``blocks_login``. It lived in
``apps.users`` until the boundary audit (step 7); the table kept its name.

Killing a restricted customer's sessions is the one thing this needs from
users, so users registers it from ``UsersConfig.ready()`` rather than this app
importing it (ADR-0033).
"""
import logging
from typing import Callable, Optional

from django.core.exceptions import ValidationError

logger = logging.getLogger(__name__)

_session_revoker: Optional[Callable] = None


def register_session_revoker(fn: Callable) -> None:
    """Register the callable that revokes every session a user holds."""
    global _session_revoker
    _session_revoker = fn


def _revoke_sessions(user) -> None:
    # A restriction that lands without its session kill would leave a
    # suspended customer signed in, so a missing registration is an error.
    if _session_revoker is None:
        raise RuntimeError(
            "No session revoker registered: apps.users must register one in ready().")
    _session_revoker(user)


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
                _revoke_sessions(user)
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
