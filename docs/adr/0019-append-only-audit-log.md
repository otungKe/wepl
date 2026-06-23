# ADR-0019: Append-only audit log

- **Status:** Accepted (implemented in `apps/audit/`)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §1.3 + finding #3 + Action Plan P1 #7.

## Context

The ledger is an immutable record of **money**, and the transactional outbox durably
records **domain events**. But *administrative* actions — who changed a community's
settings, who removed a member, who transferred ownership, who reset a PIN, who approved
a payout — are **not recorded anywhere queryable**. At scale this is a compliance and
incident-response blocker: support and security cannot answer "who did this, when, from
where" for anything outside the money tables.

## Decision

Introduce a dedicated, **append-only** `apps/audit` app:

- **`AuditEvent(actor, actor_label, action, target_type, target_id, tenant, metadata,
  ip_address, request_id, created_at)`** — `actor` is `SET_NULL` so history survives user
  deletion, with `actor_label` a denormalised snapshot that survives anonymisation. It is
  **append-only**: `save()` refuses updates and the model exposes no edit/delete path; the
  admin is strictly read-only.
- **`AuditService.log(action, *, actor, target=…, metadata=…, tenant=…, request=…)`** — one
  tiny call. It snapshots the actor label, derives `target_type/target_id` from a passed
  object, resolves the tenant (explicit, else the pinned RLS tenant), and stamps the current
  `request_id` (from `core.middleware`) for log correlation.
- **Written inside the action's transaction.** Audit calls live in the `@transaction.atomic`
  service methods, so a rolled-back action leaves no audit row and a committed one always
  has one.

### First consumers (this PR)

Community administration and the security/money-adjacent admin actions already in the tree:

| action | where |
|---|---|
| `community.role_changed` | `CommunityService.assign_role` |
| `community.member_removed` | `CommunityService.remove_member` |
| `community.ownership_transferred` | `CommunityService.transfer_ownership` |
| `community.settings_updated` | `CommunityUpdateView` |
| `community.deleted` | `CommunityDeleteView` |
| `auth.pin_reset` | `ResetPINView` |
| `welfare.claim_approved` / `welfare.claim_rejected` | `WelfareService` |
| `advance.approved` / `advance.rejected` | `EmergencyAdvanceService` |

## Consequences

- **+** A queryable, tamper-resistant trail for the review's "mandatory" admin actions.
- **+** One-line adoption; the service is domain-agnostic, so remaining call sites are easy.
- **+** `actor` survives user deletion (SET_NULL + label snapshot) — history isn't orphaned.
- **−** A write per audited action (negligible; these are low-frequency admin operations).
- **−** Not cryptographically chained (no hash-linking); "append-only at the app layer."
  Sufficient for v1; a tamper-evident chain can be layered later if compliance requires it.

## Deferrals (fast-follow)

- **KYC decisions** (approve/reject) — these happen in the Django admin; auditing them needs
  admin-action hooks, a slightly different seam. The model/service are ready.
- **Permission grants / staff role changes**, and **disbursement/amendment vote** events.
- Optionally **subscribe to the outbox `domain_event` signal** to auto-capture a class of
  events without per-call-site wiring (the eventing spine already exists).

## Alternatives considered

- **Reuse the outbox only.** Rejected as the primary store: the outbox is a *delivery* queue
  (consumed/pruned), not a durable query surface, and most admin actions don't `emit()` today.
  Subscribing to it is a complementary future source, not a replacement.
- **Per-app log tables.** Rejected — fragmentation; a single typed table with `target_type`
  is queryable across domains.
