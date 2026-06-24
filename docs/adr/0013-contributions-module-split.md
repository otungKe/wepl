# ADR-0013: Contributions module split (god-service decomposition)

- **Status:** Accepted (services split implemented; lifecycle state machine deferred)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §2.5 + finding #5 + Action Plan P1 #9.

## Context

`apps/contributions/services.py` was **1,919 lines** holding eight services across
five bounded contexts (savings/pool, ROSCA, welfare, shares, advances) plus
disbursements, amendments and join-requests. It was past the point one person can
hold in their head — the exact anti-pattern the ledger core avoided. The review
flagged it (and `contributions/views.py`, `users/views.py`) as "god modules."

## Decision

Split `services.py` into a **package, one module per sub-domain**, without changing
the public import surface:

```
apps/contributions/services/
  __init__.py        # re-exports every service + the public _notify/_dn helpers
  _common.py         # shared imports + helpers (_dn, _notify, _compute_next_run)
  contribution.py    # ContributionService
  rosca.py           # ROSCAService
  disbursement.py    # DisbursementService
  welfare.py         # WelfareService
  advances.py        # EmergencyAdvanceService
  standing_orders.py # StandingOrderService
  amendments.py      # AmendmentService
  join_requests.py   # ContributionJoinRequestService
```

- **Behaviour-preserving, pure move.** Code is unchanged; only its file home moved.
- **Public API unchanged.** `from apps.contributions.services import ContributionService`
  (and `_notify`, used by `users`/`mpesa`/`tasks`) still resolve — `__init__.py`
  re-exports them. ~12 call sites across the codebase needed **zero** edits.
- **Shared helpers** (`_dn`, `_notify`, `_compute_next_run`, `_emit_event`, `logger`,
  and the common model/ledger imports) live in `_common.py`, exposed via an explicit
  `__all__`; each module does `from ._common import *`. The one cross-module
  dependency (`join_requests` → `ContributionService`) is an explicit import.

## Consequences

- **+** Each sub-domain is now a focused, independently-readable ~120–300 line module.
- **+** Future work (e.g. a per-domain lifecycle state machine) has an obvious home.
- **+** Smaller blast radius for changes; easier ownership.
- **−** `from ._common import *` is a star-import (kept deliberately to make the move
  zero-diff per body); the explicit `__all__` bounds it. Imports can be tightened
  per-module later if desired.

## Deferred

- **Lifecycle state machine** (the other half of the review's ADR-0013): enforce
  status transitions (`draft→active→closed→archived`, `request→approved/rejected→
  executed`) with allowed edges + a DB check, centralising transitions. Separate PR.
- **`contributions/views.py` (1,114) and `users/views.py` (901)** decomposition into
  per-area view modules — follow-up PRs, same re-export pattern.

## Alternatives considered

- **Leave it as one file.** Rejected — the review's explicit P1 item; the size actively
  impedes change.
- **Split *and* tighten every import per module in one go.** Rejected for this PR —
  it would turn a safe, reviewable move into a large diff per body; the `_common`
  star-import keeps the change mechanical and verifiable (full suite green, unchanged).
