"""
Back Office RBAC — the capability layer (P0).

Roles are Django Groups named ``ops:<role>``; capabilities are dotted strings
(``ledger.adjust``) grouped by operational domain. The role → capability map
below is the single source of truth and is enforced *server-side* by
``RequireCapability`` — the web console only uses ``/api/ops/me/`` to decide what
to render.

Design notes
------------
* Maker-checker is object-level (enforced in the approvals flow), not encoded in
  the capability alone; a ``*.approve`` capability means "may act as a checker",
  never "may approve my own request".
* Superusers implicitly hold every capability (break-glass).
* Adding a capability here + granting it to roles is all that a new module needs
  to become access-controlled.
"""
from __future__ import annotations

# ── Capability catalogue (dotted: <domain>.<action>) ─────────────────────────
# Kept flat and explicit so the set is auditable at a glance.
CAPABILITIES: set[str] = {
    "dashboard.view",
    "search.global",
    # Users
    "users.view", "users.manage",
    # Support
    "support.view", "support.act",
    # Verification
    "verification.view", "verification.decide",
    # Financial operations
    "finops.view", "finops.retry", "finops.approve",
    # Ledger (immutable; adjust = propose a maker-checked balanced entry)
    "ledger.view", "ledger.adjust", "ledger.export",
    # Transactions
    "transactions.view",
    # Treasury
    "treasury.view", "treasury.act",
    # Risk & compliance
    "risk.view", "risk.decide",
    # Approvals (dual-control inbox)
    "approvals.view", "approvals.decide",
    # Reconciliation
    "reconciliation.view", "reconciliation.act",
    # Communities
    "communities.view", "communities.manage",
    # Reporting
    "reporting.view", "reporting.export",
    # Audit (read-only surface)
    "audit.view", "audit.export",
    # System health
    "health.view", "health.act",
    # Configuration (change is always maker-checked)
    "config.view", "config.change",
    # Developer tools
    "devtools.view", "devtools.act",
}

# Every operator can see their dashboard and use global search.
_BASE = {"dashboard.view", "search.global"}

# ── Roles (Django Group name → capabilities) ─────────────────────────────────
ROLE_PREFIX = "ops:"

ROLE_CAPABILITIES: dict[str, set[str]] = {
    "operations": _BASE | {
        "users.view", "communities.view", "communities.manage",
        "transactions.view", "finops.view", "finops.retry",
    },
    "support": _BASE | {
        "support.view", "support.act", "users.view",
        "communities.view", "transactions.view",
    },
    "finance": _BASE | {
        "ledger.view", "ledger.adjust", "ledger.export",
        "finops.view", "finops.retry", "finops.approve",
        "transactions.view", "reconciliation.view", "reconciliation.act",
        "treasury.view", "reporting.view", "reporting.export", "approvals.decide", "approvals.view",
    },
    "treasury": _BASE | {
        "treasury.view", "treasury.act", "ledger.view",
        "reconciliation.view", "reporting.view", "reporting.export",
        "approvals.view", "approvals.decide",
    },
    "compliance": _BASE | {
        "verification.view", "verification.decide", "risk.view",
        "users.view", "audit.view", "audit.export",
        "reporting.view", "reporting.export", "approvals.view", "approvals.decide",
    },
    "risk": _BASE | {
        "risk.view", "risk.decide", "transactions.view",
        "users.view", "approvals.view",
    },
    "verification": _BASE | {
        "verification.view", "verification.decide", "users.view",
    },
    "auditor": _BASE | {
        # Read-everything, change-nothing.
        "users.view", "support.view", "verification.view", "finops.view",
        "ledger.view", "ledger.export", "transactions.view", "treasury.view",
        "risk.view", "approvals.view", "reconciliation.view", "communities.view",
        "reporting.view", "reporting.export", "audit.view", "audit.export",
        "health.view", "config.view",
    },
    "analyst": _BASE | {
        "reporting.view", "reporting.export", "transactions.view", "communities.view",
    },
    "developer": _BASE | {
        "health.view", "health.act", "devtools.view", "devtools.act",
    },
    # super_admin is handled by the is_superuser short-circuit, but the group is
    # seeded so it can be assigned; it resolves to the full catalogue.
    "super_admin": set(CAPABILITIES),
}

ALL_ROLES = list(ROLE_CAPABILITIES.keys())


def group_name(role: str) -> str:
    return f"{ROLE_PREFIX}{role}"


def roles_for(user) -> list[str]:
    """The ops role slugs a user holds (via ``ops:*`` group membership)."""
    if user is None or not user.is_authenticated:
        return []
    names = user.groups.values_list("name", flat=True)
    return sorted(n[len(ROLE_PREFIX):] for n in names if n.startswith(ROLE_PREFIX))


def capabilities_for(user) -> set[str]:
    """Union of capabilities across a user's ops roles. Superusers get all."""
    if user is None or not user.is_authenticated:
        return set()
    if user.is_superuser:
        return set(CAPABILITIES)
    caps: set[str] = set()
    for role in roles_for(user):
        caps |= ROLE_CAPABILITIES.get(role, set())
    return caps


def has_capability(user, capability: str) -> bool:
    if user is None or not user.is_authenticated or not getattr(user, "is_active", True):
        return False
    if user.is_superuser:
        return True
    return capability in capabilities_for(user)


def is_operator(user) -> bool:
    """An active staff account that belongs to at least one ops role (or is a
    Platform Super Admin)."""
    if user is None or not user.is_authenticated or not getattr(user, "is_active", True):
        return False
    return user.is_superuser or bool(roles_for(user))
