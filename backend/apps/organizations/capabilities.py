"""
Organization capability layer (ADR-0026 §4 — the capability architecture).

The org-level analogue of ``backoffice/capabilities.py``: where that governs what
a *staff operator* may do inside the console, this governs what an *organization*
may do on the platform — operate a welfare program, collect via M-Pesa, take
deposits, participate in clearing.

Three tiers, mirrored from the strategy doc (§4):

1. **Universal kernel** — capabilities every organization holds (membership,
   ledger read, payment rails, communications, documents, audit, and the three
   program types Wepl operates today). This is what Wepl has already built; every
   archetype starts here.
2. **Regulated capabilities** — compliance-gated grants (deposit-taking, lending,
   fund distribution, clearing). Vocabulary only for now: no current archetype is
   granted them, and the community ceiling forbids them outright.
3. **Archetype bundles** — a curated default set per archetype so a chama works
   with zero configuration.

Two invariants keep the spine honest (ADR-0026):

* **Archetype is metadata, not taxonomy.** Domain code asks ``has_capability``,
  never ``if org.archetype == …``. The archetype only *selects a bundle*.
* **The archetype is a ceiling that cannot be exceeded.** ``ceiling_for`` is the
  set an archetype may *ever* hold; a grant outside it is a bug, not a config
  option. A chama can never be granted ``deposit.take`` — that needs a different
  archetype with its own KYB and regulatory posture.

Deliberately **not** here yet (rule of three; the strategy's anti-inner-platform
defense, §4): a per-org grant store. With one archetype whose bundle equals its
ceiling, the bundle *is* the effective grant. The grant table lands with the
first regulated archetype/capability (Phase 1 counterparty / Phase 2 SACCO),
when there is a real grant to record and audit — extracted from a concrete case,
not speculated.
"""
from __future__ import annotations

from apps.organizations.models import Organization


# ── Capability catalogue (dotted: <domain>.<action>) ─────────────────────────
# Universal kernel — held by every organization.
KERNEL: frozenset[str] = frozenset({
    "membership.manage",     # add/remove members, assign org-scoped roles
    "program.contribution",  # operate a contribution / pool program
    "program.welfare",       # operate a welfare-fund program
    "program.shares",        # operate a shares-fund program
    "ledger.read",           # read its own ledger / statements
    "payments.collect",      # collect via payment rails (STK push)
    "payments.payout",       # disburse via payment rails (B2C)
    "communications.send",   # notifications / chat
    "documents.manage",      # its own documents
    "audit.read",            # its own audit trail
})

# Regulated capabilities — compliance-gated, archetype-ceilinged. Vocabulary for
# archetypes that do not exist yet; no current archetype may hold these, and the
# community ceiling excludes them. Listed so the ceiling can *exclude* them
# explicitly rather than by omission.
REGULATED: frozenset[str] = frozenset({
    "deposit.take",          # deposit-taking institution (SACCO)
    "credit.lend",           # lending / loan facilities
    "insurance.premium",     # premium collection
    "fund.distribute",       # money-market / fund distribution (Phase-1 counterparty)
    "clearing.participate",  # cross-org settlement spine (Phase 1, heaviest weight)
})

CAPABILITIES: frozenset[str] = KERNEL | REGULATED

# Program type → the capability an org needs to operate it. Consulted by
# ``ensure_program`` so provisioning a program is a capability-gated act.
PROGRAM_CAPABILITY: dict[str, str] = {
    "contribution": "program.contribution",
    "welfare":      "program.welfare",
    "shares":       "program.shares",
}


# ── Archetype bundles + ceilings ─────────────────────────────────────────────
# bundle  = granted at birth (the effective grant today).
# ceiling = may *ever* be granted; a grant outside it is a bug (bundle ⊆ ceiling).
# The only archetype today is COMMUNITY: a chama is member-money mutual aid, so
# its ceiling equals the kernel — it may never take deposits, lend, or clear
# between organizations. Those require a different archetype entirely.
_ARCHETYPE: dict[str, dict[str, frozenset[str]]] = {
    Organization.Archetype.COMMUNITY: {
        "bundle":  KERNEL,
        "ceiling": KERNEL,
    },
}

_EMPTY = frozenset()


class CapabilityError(Exception):
    """An organization was asked to do something its capabilities don't permit."""


def _entry(archetype: str) -> dict[str, frozenset[str]]:
    return _ARCHETYPE.get(archetype, {"bundle": _EMPTY, "ceiling": _EMPTY})


def bundle_for(archetype: str) -> frozenset[str]:
    """Capabilities an archetype holds by default — its effective grant today."""
    return _entry(archetype)["bundle"]


def ceiling_for(archetype: str) -> frozenset[str]:
    """Capabilities an archetype may *ever* hold. A grant outside this is a bug."""
    return _entry(archetype)["ceiling"]


def capabilities_for(org: Organization | None) -> frozenset[str]:
    """Effective capability set for an organization.

    ``None`` (a personal / open pool operated by an individual, not yet an org)
    resolves to the kernel: a person acting for themselves already holds the
    universal kernel through their own identity, which is what keeps standalone
    contributions working unchanged.
    """
    if org is None:
        return KERNEL
    return bundle_for(org.archetype)


def has_capability(org: Organization | None, capability: str) -> bool:
    return capability in capabilities_for(org)


def require_capability(org: Organization | None, capability: str) -> None:
    """Assert ``org`` may perform ``capability``; raise ``CapabilityError`` if not.

    The enforcement seam that regulated flows and program provisioning hang on.
    For the community archetype (whose bundle is the full kernel) this is inert;
    it becomes load-bearing the moment an archetype with a narrower bundle exists.
    """
    if not has_capability(org, capability):
        who = f"organization {org.uid}" if org is not None else "an individual"
        arche = getattr(org, "archetype", None)
        raise CapabilityError(
            f"{who} lacks capability {capability!r} (archetype {arche!r})."
        )
