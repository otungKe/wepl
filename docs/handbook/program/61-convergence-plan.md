# Program / 61 — Convergence Plan

> **Where we start.** The handbook is the target; this is the plan that moves the
> *existing* code onto it. Wepl is not being rewritten — it is being **converged**:
> the record is reconciled to the code, the code is cleaned to obey the constitution,
> and the next frontier (BaaS) is opened. "Build clean" here means *converge and
> clean up*, never *greenfield rewrite* — because P-7/E-2 forbid deleting working
> money code on faith, and the ledger core is already correct and CI-guarded.

This plan is grounded in the real repo state (July 2026), the
[2026-06 audit](../../audit/2026-06-architecture-audit.md), and the open GitHub
epics (#4–#13, #57). It complements — does not replace — the
[roadmap](60-roadmap-and-milestones.md).

---

## The honest starting assessment

Two facts, both established by reading the code rather than assuming:

1. **The dangerous legacy is already gone.** The single-entry `LedgerEntry`,
   `ContributionAccount`, and mutable balance caches were deleted in Phase 0; a
   grep-guard fails CI if they return. Zero occurrences remain outside
   migrations/tests. The scary rewrite has *already happened* and succeeded.
2. **The remaining "noise" is bounded and ordinary.** ~40 TODO/FIXME-class markers
   across ~26k lines of app code (low), a handful of large files
   (`contributions/models.py` 833, `communities/services.py` 790, `mpesa/views.py`
   645), some quarantined legacy tests (issue #14), one lingering provider-leak
   fallback, and stale docs. This is **hygiene, not reconstruction.**

The correct posture, therefore, is **evolve + clean**, organised into four
workstreams below. None of them requires relaxing a principle; all of them are
additive-first.

## The work-item convention

Convergence items use **`CV-{nn}`** (mirrors `P{phase}-{nn}` / `UX-{nn}`), referenced
in commits and PRs, mapped to existing GitHub epics where one applies. Definition of
Done is the roadmap's: *code merged · acceptance criteria met · tests green · docs/ADR
updated · checkbox ticked.*

---

## Workstream A — Reconcile the record (make the handbook true)

*Cheapest, highest-trust. Docs-only; no runtime risk. Do first.*

The [Charter](../00-charter.md) forbids code and record diverging silently. Several
ADRs are marked **Proposed** though their code has shipped and is in production.

| ID | Item | Acceptance | Principle |
|----|------|-----------|-----------|
| **CV-01** | ✅ **Done (2026-07-11).** Rebuild the stale ADR index (it listed 10 of 25, mismarked 0005/0006/0007/0025 as *Proposed*) and promote ADR-0005 to Accepted. Reality: **all ADRs Accepted except 0024.** | ADR index complete + accurate; 0005 Accepted | P-20 |
| **CV-02** | Resolve ADR-0024 — the only remaining *Proposed*: fee postings shipped, but excise-duty/withholding await business/compliance inputs. Decide and either accept or scope the tax legs. | 0024 status reflects a real decision, not drift | P-20 |
| **CV-03** | Write ADRs for any decision made only in code (audit the money path for undocumented structural choices) | Every structural decision has an ADR | P-20 |
| **CV-04** | Reconcile the handbook status table + stale cross-refs against current code | Handbook README status table is honest; link-check passes | Charter |

**Exit:** an auditor reading `docs/` and the code finds no silent divergence.
**Finding on first pass:** the record *had* drifted (stale ADR index) — now fixed.
This validates the whole workstream: the divergence was real and invisible until
someone read both.

---

## Workstream B — Close the tracked gaps (make the code obey the constitution)

*The audit's and handbook's named gaps, turned into work items.*

| ID | Item | Acceptance | Ref |
|----|------|-----------|-----|
| **CV-10** | **Split Celery from the web dyno** — worker + beat as independently deployed/scaled services | `render.yaml` runs separate worker/beat; async burst can't degrade request latency | Infra R6; P0-01; [Infrastructure](../operations/50-infrastructure.md) |
| **CV-11** | **Mechanize module boundaries** — add an `import-linter` contract enforcing the [dependency rules](../architecture/22-module-boundaries.md) (ledger imports no product; nothing bypasses a port) | CI fails on a boundary violation; Rule 1/Rule 3 are machine-checked | E-14; [Future Evolution](63-future-evolution.md) |
| **CV-12** | **Confirm/settle KYC-media durability** — verify S3/R2 is the only media path in every environment; no ephemeral-disk fallback | KYC media provably on object storage in prod; test asserts it | R5; [Security](../architecture/25-security-architecture.md) |
| **CV-13** | **Extend the grep-guard family** — add guards for newly-identified dangerous patterns beyond the legacy-ledger guard | New guards merge-blocking in CI | P-22 |
| **CV-13a** | ✅ **Done (2026-07-11).** CI guard `no change-history narration in code comments` — fails the build on work-item IDs / PR-issue refs in `apps/*.py` | Guard merge-blocking; tree clean | P-22 |

**Exit:** every gap the handbook currently "names" is closed or is itself a tracked
work item with a date.

---

## Workstream C — Clean the noise (the "build clean" mandate)

*Bounded, additive cleanup. This is the workstream that answers the concern directly.*

| ID | Item | Acceptance | Ref |
|----|------|-----------|-----|
| **CV-20** | **Discharge issue #14** — rewrite the quarantined legacy money-path tests against `post_journal()`, then remove the `@skip`s | No skipped money-path tests; suite green with them enabled | #14; P-7 |
| **CV-21** | **Fix real bug #1 from #14** — `_check_governance_deadlock` crashes for percentage thresholds (`_ProxyContribution` passed where a model instance is required) | A contribution with a numeric `voting_threshold` posts without `TypeError`; regression test added | #14; [Governance](../domain/13-governance-architecture.md) |
| **CV-22** | **Resolve real bug #2 from #14** — solo-contribution creation blocked by the disbursement quorum check (product decision: gate *disbursement*, not *creation*) | Creating a solo/open contribution succeeds; disbursement still gated | #14 |
| **CV-23** | **De-couple the ledger from the M-Pesa adapter** *(rescoped 2026-07-11 — the old `_legacy_b2c_result` fallback is already gone; this is the real, larger leak).* The **ledger violates its own cardinal rule**: `apps/ledger/tasks.py` imports `apps.mpesa` (`MpesaService`, `_on_b2c_success`) to orchestrate B2C payouts, and `FinancialTransaction` carries Daraja field names (`mpesa_checkout_id`, `mpesa_conversation_id`, `mpesa_receipt`). Move payout *orchestration* into `payments` (ledger only *records* confirmed movement) and rename/abstract the provider-reference fields behind the port. | `apps.ledger` imports nothing from `apps.mpesa`; no Daraja vocabulary in ledger models; CV-11 import-linter enforces it | **Rule 1 / P-18**; needs its own ADR |
| **CV-24** | **Trim the god modules** — split `contributions/models.py` (833), `communities/services.py` (790), `mpesa/views.py` (645) along sub-domain seams | No non-test app file > ~500 lines without a documented reason; boundaries intact | R8; [ADR-0013](../../adr/0013-contributions-module-split.md) |
| **CV-25** | **Sweep the ~40 noise markers** — resolve or convert each TODO/FIXME/HACK into a tracked issue; delete dead/experimental code additively | Marker count materially reduced; nothing dead left in tree | E-2 |
| **CV-25a** | ✅ **Done (2026-07-11).** Strip all change-history narration from code comments/docstrings (work-item IDs, phase/PR/audit-finding refs) across ~90 files; ADR references preserved. Establishes the clean **reference baseline**. | No history narration in code; CV-13a guard green; suite passes | E-2, Charter |
| **CV-26** | **Prune/refresh stale docs** — reconcile `docs/*Communities_*` audits and older planning docs against current reality; archive or update | No doc contradicts current code without being marked a dated snapshot | [Documentation Standards](../engineering/35-documentation-standards.md) |

**Exit:** the codebase *feels* as clean as it *measures* — no skipped money tests, no
provider leak, no god modules, no dead code, no contradictory docs. And CV-11's
import-linter means the cleanliness is now **defended by CI**, so it can't silently
re-accumulate.

---

## Workstream D — Open the next frontier (Phase 7, BaaS)

*The first genuinely new build. Decisions before code (P-20).*

Phase 7 (epic #11, `P7-01..06`) is the only "Not started" phase and the
[Vision](../product/01-vision.md)'s endgame. It begins with ADRs, not endpoints.

| ID | Item | Acceptance | Ref |
|----|------|-----------|-----|
| **CV-30** | **ADR — public API shape & versioning** (path/header versioning, deprecation policy, OpenAPI as SDK source) | ADR-0026 accepted | P7-01; [API](../architecture/23-api-architecture.md) |
| **CV-31** | **ADR — per-tenant API-key auth** (keys/scopes/rotation/rate limits, distinct from user JWTs) | ADR-0027 accepted | P7-02; [Security](../architecture/25-security-architecture.md) |
| **CV-32** | **ADR — outbound webhooks on the outbox** (signing, retries, at-least-once, receiver dedupe) | ADR-0028 accepted; webhooks are *outbox consumers*, not new infra | P7-03; [Eventing](../architecture/26-eventing-architecture.md) |
| **CV-33** | **ADR — sandbox model** (`FakeProvider` rails + fake identity behind a tenant) | ADR-0029 accepted | P7-04; [Payments](../architecture/27-payments-architecture.md) |
| **CV-34** | Then implement `P7-01..06` behind those decisions | Third party opens a wallet, moves money, receives a signed webhook — in sandbox | epic #11 |

**Precondition (hard gate):** CV-11 (boundary contract) and exhaustive **tenant
isolation tests** land *before* any external traffic — cross-tenant leakage (R11) is
the defining BaaS risk.

**Exit:** the [M6 milestone](60-roadmap-and-milestones.md) — others build on Wepl.

---

## Sequencing

```
  A (reconcile record)  ──┐  docs-only, do immediately, no runtime risk
                          ├─► B (close gaps)  ──┐  makes code obey the constitution
  C (clean noise)  ───────┘                     ├─► D (Phase 7 / BaaS)
      ▲ CV-20..23 unblock a trustworthy suite    │      gated on CV-11 + isolation tests
      └───────────────────────────────────────────┘
```

- **A** is pure documentation — start today, zero risk.
- **B** and **C** run in parallel; together they are "build clean." **CV-20/21/22**
  (discharge #14) and **CV-23** (kill the provider leak) are the highest-value
  cleanups because they remove *correctness* debt, not just cosmetic debt.
- **D** (Phase 7) starts with ADRs (which can be written in parallel with B/C) but
  its *implementation* is gated on CV-11 + tenant-isolation testing.

## What this plan deliberately refuses

- **No greenfield rewrite.** The ledger core is correct and CI-guarded; rewriting it
  would re-earn correctness we already hold (P-7, E-2).
- **No "clean up" that relaxes an invariant.** Cleanup is additive; the trial balance
  stays zero throughout (P-6).
- **No new money path, port leak, or plane mix introduced while cleaning.** Cleanup
  obeys the same principles as feature work.
- **No Phase 7 code before the boundary contract and isolation tests.** Opening the
  platform on un-mechanized boundaries is how cross-tenant leakage happens.

## How this maps to GitHub

The roadmap epics already exist (#4–#13); Phase 7/8 are #11/#12. The convergence
work is tracked as either (a) a new **"Convergence & Cleanup" epic** seeding
`CV-{nn}` sub-issues, or (b) `CV` items attached to the existing epic they close
(e.g. CV-20/21/22 → #14, CV-23 → #5, CV-10 → #13/P0-01). See
[Getting Started](../GETTING-STARTED.md) for how to claim one.

---

*Continue to [Getting Started](../GETTING-STARTED.md), or back to
[Roadmap & Milestones](60-roadmap-and-milestones.md).*
