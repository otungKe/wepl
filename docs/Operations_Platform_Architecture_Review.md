# Operations Platform — Continuous Architecture Review

Standing review of the Operations Platform direction against the code on
master. Written as the implementation's architectural position: what the
proposed refinements get right, where the codebase argues for something
different, and the rules being enforced going forward. Three items need an
explicit decision (§8) before they shape code.

**State of the boundary today** (verified, not aspirational): the ops context
(`apps/backoffice`) performs **zero direct domain writes** — its only ORM write
is `StaffAccount.last_login`, its own model. Every mutation routes through a
domain service: verification decisions → `apps.verification.service.decide /
decide_subject_case`, community lifecycle → `CommunityService.suspend/
unsuspend`, EDD clearances → the same single doors the customer flows use.
The principle "operations orchestrates, domains own logic" is not a target —
it is the current, test-enforced reality. The job of this review is to keep it
that way as modules multiply.

---

## 1. Bounded context: keep one Django app; do not rename, do not pre-split

**Proposal**: `apps/ops/` with ~14 sub-packages (dashboard/users/communities/
verification/finance/treasury/ledger/reporting/permissions/staff/support/
risk/investigations).

**Position: keep `apps/backoffice` as a single Django app; grow packages
inside it when a workspace earns one; never rename.**

- Renaming `backoffice` → `ops` is a migration-history operation (the app
  label is baked into `StaffAccount` migrations and every FK to it —
  `CaseEvent.actor_staff`, `ControlOverride`… wait, overrides carry no staff
  FK; `CaseNote.author_staff`, `VerificationCase.assigned_to`). A Django app
  rename is real risk purchased for a cosmetic word. Rejected.
- Fourteen sub-apps for ~4 live workspaces is structure ahead of substance —
  the proposal itself says "only create them when implementation justifies";
  today that test passes for none of them. The existing convention —
  `views_<workspace>.py` per module, shared `capabilities/permissions/audit/
  auth` spine — is the same shape at the right scale.
- The evolution path when a workspace outgrows one file is already
  established in this codebase: the `apps/users/views/` package split
  (ADR-0013). When `views_verification.py` (the largest, ~600 lines) needs
  it, it becomes `backoffice/verification/` as a *package*, not a new Django
  app. Same for future finance/treasury workspaces.
- One deliberate exception to "one app": if **investigations** ever becomes a
  real domain (cross-entity case files with their own lifecycle, evidence,
  and retention), that is a *domain app* like `apps/verification`, not an ops
  workspace — operations would orchestrate it like everything else. Naming it
  now would be speculation; noting the boundary rule is the useful part.

**Rule enforced**: new ops workspace ⇒ new `views_<name>.py` + capability
entries + `record_action` on every mutation + tests. Promotion to a package
only on size, never pre-emptively.

## 2. The read/write asymmetry is the load-bearing rule — codify it

The principles say "compose through services, never direct model
manipulation." Applied literally to *reads*, that would force every ops list
endpoint through domain-service indirection that exists only for ceremony.
The pattern actually working on master is sharper:

- **Writes: domain services only.** No exceptions; a `.save()` on a domain
  model inside `apps/backoffice` fails review. (Current violations: none.)
- **Reads: the ops context may query domain models directly.** Ops screens
  are cross-domain *projections* — the community file joins communities,
  contributions, audit; the dashboard joins six domains. Forcing each read
  through a per-domain "service" would duplicate queryset code and slow every
  screen for no invariant gained, because reads cannot corrupt state.
- Two hygiene bounds on the read privilege: (a) no reliance on domain
  *private* helpers — `views_verification` currently calls
  `case_service._held_movement_for`; that helper should lose its underscore
  and become part of the service's public read surface (small cleanup,
  queued); (b) heavy/reusable read logic (e.g. `has_financial_history`)
  lives in the domain service, not in an ops view — already the case.

This is CQRS at the pragmatic scale this platform needs, and it should be the
review test for every future ops PR.

## 3. 360 views: composed reads, never stored aggregates

Agreed as the organizing idea for ops screens — with three corrections:

- **A 360 is an endpoint, not a table.** `OpsCommunityDetailView` and the
  verification case file are the pattern: composed at read time from the
  owning domains. The moment a 360 gets its own persisted/denormalised store,
  it becomes a second source of truth that drifts. If a 360 ever gets slow,
  the fix is caching or per-block lazy loading, not materialisation.
- **Challenge: "Wallet 360" must not exist.** There is no wallet in this
  architecture — balances are derived ledger projections (ADR-0002/0003), and
  naming an ops view "wallet" will, over time, recruit a wallet *concept*
  (stored balances, wallet ids) back into the platform. The entity is a
  **Member Financial 360**: the user's ledger accounts, balances from the
  projection, movement history, holds, overrides. Same data, safe name.
- **Sequencing by pull, not by list**: User 360 is next (support + risk both
  need it; most blocks already exist: profile, KYC/case state, memberships,
  sessions, financial summary via existing enrichment). Then Transaction 360
  with the FinOps module. Contribution 360 rides on it. Staff 360 is a thin
  page over StaffAccount + its audit trail whenever staff-management lands.
  Tenant 360 waits for P6-04 — building it now would be a view over one row.

**Placement test for any block** ("is this information in the correct
360?"): the block belongs to the entity whose *lifecycle* explains it, and is
*linked* (not duplicated) elsewhere — the community file shows the count of
open EDD cases with a link; the case file owns the case detail. Duplication
of data across 360s is fine (they're projections); duplication of *aggregation
logic* is not — shared blocks become domain-service query helpers.

## 4. Staff & permissions: challenge accepted — a flatter, more auditable target

**Proposal**: Permission → Role Template → Department Template → Staff →
Individual Overrides, evolving to RBAC + ABAC.

**Position: two of the five layers are liabilities in a regulated platform.
Recommend a flatter hierarchy with append-only delegation.**

- **Individual permission overrides are an audit anti-feature.** The moment
  per-person grants exist as silent state, "who can approve payouts?" stops
  having a table answer and becomes a per-person investigation; separation-
  of-duties review degrades from reading one file to auditing N staff rows.
  Financial institutions that implemented individual overrides spend audit
  seasons unwinding them.
- **Department templates add a second grouping dimension with murky
  semantics** (what does the Risk department template grant a Verification
  Officer that the role doesn't?). Departments are real — as *organisational
  metadata* on StaffAccount (display, reporting lines, escalation routing),
  not as a permission layer.
- **Recommended target**:

  ```
  Capability (code-defined, auditable in one file)
      ↓
  Role template (code-defined map — capabilities.py, as today)
      ↓
  Staff member (N roles via ops:* groups — already M2M, already works)
      +
  Time-boxed, audited GRANTS (the delegation escape valve)
  ```

  A **grant** is what an override should have been: an explicit row —
  capability, staff member, granter, reason, expiry — append-only, visible in
  the audit log, auto-expiring. It covers every legitimate override story
  ("cover approvals while X is on leave") without creating permanent
  invisible power. Build it when the first real delegation need appears, not
  before.
- **ABAC arrives as guards, not an engine.** The platform already has the
  seams: `RequireStepUp` (stub awaiting the step-up auth decision), tenant
  pinning, amount thresholds (maker-checker will gate on amount). Attribute
  rules belong at the action site as policy guards — a generic ABAC engine is
  a platform project this platform does not need.

## 5. Dashboard providers: right idea, armed with a trigger, not built today

`OpsMetricsView` is one function of six capability-gated blocks — readable,
tested, and each block already *is* a provider in miniature (capability +
key + queries). Extracting a provider registry now would be refactoring a
70-line function into infrastructure. **Trigger to build it**: when blocks
exceed ~10, or any block needs caching/timeout isolation (one slow domain
must not stall the dashboard), or a second consumer of the metrics appears
(reporting). Until then, new tiles are new gated blocks in the same view —
and every block must remain capability-filtered server-side, which is the
non-negotiable part.

## 6. Stability map: three corrections from the ground

| Claimed | Reality check |
|---|---|
| Ledger, Tenancy, Auth, Audit stable | **Agree** — tenancy is stable *scaffolding* (resolution stubbed until P6-04; don't restructure, but don't call the mapping settled). |
| "Reporting foundations" stable | **There is no reporting app.** Foundations = coded rejections, stats endpoints, audit trail — those are stable, but there is nothing to hold still. Remove from the list until it exists. |
| Notifications evolving | **More stable than claimed** — outbox + receiver + event-id dedupe (ADR-0006) hasn't structurally moved in months and every module now rides it. Treat the *pipeline* as stable; only notification *content/channels* evolve. |
| Communities evolving | **Recently hardened** — the 3-sprint audit remediation (lifecycle, safe delete, bans, eventing) moved it from the platform's weakest module to one governed by declared rules. Still product-evolving (M-5 pagination, announcements), but its *architecture* (policy table, service door, outbox) should now be treated as stable and defended. |
| "Social" evolving | No social app exists; `activity` + `conversations` are the nearest — both genuinely evolving. Name them, not "Social". |
| Contributions, Payments evolving | **Agree** — contributions is the largest evolving surface; payments is stable at the port/adapter boundary (ADR-0005) but the M-Pesa adapter is sandbox-hardened only. |

Repository consequence: **no directory moves anywhere.** Django app labels
live inside migration history; renames are risk without value. Evolution
happens inside apps (view packages, service splits), never by relocation.

## 7. Standing review checklist (what every ops PR is held to)

1. Mutations call a domain service; the diff contains no domain `.save()`.
2. Every mutation calls `record_action`; domain-visible changes also land on
   the domain's own trail (the suspend lever writes both — the model case).
3. Every endpoint declares a capability; metrics/search filter server-side.
4. New workspace = capability entries + tests incl. a 403 test.
5. Cross-tenant: ops reads span tenants by design (no pinned tenant on staff
   requests); anything tenant-scoped must say so explicitly.
6. Reads may join domain models; they may not import domain privates or
   re-implement a rule that exists as a service helper.
7. No stored aggregates for 360s; no balance-like columns anywhere, ever.

## 8. Decisions — RULED (adopted as recommended)

1. **Permissions target — DECIDED**: capability → role template → staff
   (multiple roles), plus time-boxed audited GRANTS as the only override
   mechanism, built when the first real delegation need appears. Departments
   are StaffAccount metadata, never a permission layer. ABAC lands as
   action-site guards (RequireStepUp, amount thresholds, tenant pinning),
   not a policy engine.
2. **"Wallet 360" — DECIDED**: the entity is **Member Financial 360**. No
   wallet concept — name or column — enters the platform; balances remain
   derived ledger projections only (ADR-0002/0003).
3. **App identity — DECIDED**: `apps/backoffice` remains the ops bounded
   context permanently. No rename; growth happens by promoting
   `views_<workspace>.py` files to packages inside the app (ADR-0013
   pattern). The external identity stays the API surface: `/api/ops/*` and
   the `"ops"` staff-JWT type.

These rulings, together with §7's checklist, govern all Operations Platform
implementation from this point.
