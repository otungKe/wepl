"""
Two-tier access model (ADR-0022).

A single, declarative gate for the KYC-behind-money policy. It complements the
resource authorization layer (apps/core/policy.py): *policy* answers "may this
actor act on this resource"; *tiers* answers "has this account unlocked full
access yet". Both raise Django exceptions so they work from services, Celery and
WebSocket consumers, and both are rendered by core.exceptions.custom_exception_handler.

Tiers (derived from verification state on User — nothing extra stored):
    Tier 0  — phone verified, KYC not approved     → discovery / read only
    Tier 1  — phone verified, KYC approved          → full access

Usage
-----
Gate a Tier-1 action (raises KYCRequired → structured 403 if not allowed)::

    from apps.users.tiers import AccessPolicy
    AccessPolicy.require_tier1(user)

Branch without raising::

    if AccessPolicy.is_tier1(user):
        ...

Extending to more tiers later: add `is_tierN` / `require_tierN` here and a matching
derived property on User; call sites stay unchanged.
"""
from apps.core.exceptions import KYCRequired


class AccessPolicy:
    """Stateless helpers around the derived tier properties on ``User``."""

    # ── Predicates (never raise) ─────────────────────────────────────────────
    @staticmethod
    def is_tier1(user) -> bool:
        return bool(user and user.is_authenticated and user.is_tier1)

    @staticmethod
    def is_tier0(user) -> bool:
        return bool(user and user.is_authenticated and user.is_tier0)

    @staticmethod
    def has_full_access(user) -> bool:
        return AccessPolicy.is_tier1(user)

    # ── Gate (raises KYCRequired) ────────────────────────────────────────────
    @staticmethod
    def require_tier1(user, message=None) -> None:
        """Allow a Tier-1 action, else raise KYCRequired (structured 403).

        Superusers/staff bypass (platform operators), mirroring the policy layer.
        """
        if user and (getattr(user, 'is_superuser', False) or getattr(user, 'is_staff', False)):
            return
        if AccessPolicy.is_tier1(user):
            return
        raise KYCRequired(message)

    # Convenience aliases so call sites read intently. All Tier-1 gated for now;
    # Phase B may add finer per-action logic here without touching call sites.
    @staticmethod
    def can_create_community(user) -> bool:
        return AccessPolicy.is_tier1(user)

    @staticmethod
    def can_contribute(user) -> bool:
        return AccessPolicy.is_tier1(user)
