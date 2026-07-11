# Program / 62 — Risks

> What could break the platform — technically, operationally, and strategically —
> and the mitigations that are (or must be) in place. This chapter is deliberately
> unflinching: a risk named is a risk managed, and a financial platform that is
> quiet about its risks is not being honest ([Philosophy §7](../product/02-philosophy.md)).

Risks are rated by **severity** (impact if realised) and **posture** (mitigated /
partially mitigated / open). Many draw on the
[2026-06 audit](../../audit/2026-06-architecture-audit.md), updated for the work
done since.

---

## R1 — A second source of truth for money reappears
**Severity: Critical · Posture: Mitigated (structurally).**
The original sin the platform was rebuilt to remove
([Financial Architecture §13](../domain/12-financial-architecture.md)). If a mutable
balance cache or a shadow ledger creeps back, drift returns.
**Mitigation:** the single money door (**P-2**), derived balances (**P-3**), and the
**CI grep-guard** that fails the build on `LedgerEntry` / `current_amount = F(...)` /
`ContributionAccount`. This risk is held down by a machine, not by memory — which is
exactly why the guard must never be disabled (E-7).

## R2 — The production OTP bypass is left on
**Severity: Critical · Posture: Mitigated (fail-closed).**
`STAGING_OTP_BYPASS=true` in production is a total auth bypass — a real High-severity
audit finding on the prod env.
**Mitigation:** `production.py` **refuses to boot** if the bypass is set while
`DEBUG=False` (**P-15**). The mistake becomes a refused deploy, not a silent breach.
**Residual:** the guard must never be weakened; treat any PR touching it as
security-critical.

## R3 — Money is mis-posted or double-posted from the rails
**Severity: High · Posture: Mitigated.**
M-Pesa callbacks are at-least-once and sometimes ambiguous; a naïve integration could
double-credit or credit on an unconfirmed push.
**Mitigation:** posting only on confirmed callbacks; **idempotency** on a unique key
(the DB enforces it); ambiguous money to **suspense** (`1100`) for reconciliation
([Payments](../architecture/27-payments-architecture.md)). The DB balance trigger
makes an unbalanced result impossible regardless.

## R4 — Customer/operator identity boundary is breached
**Severity: Critical · Posture: Mitigated (structurally).**
An escalation from a customer to operator identity would be catastrophic.
**Mitigation:** two populations, separate credentials, separate tokens, **separate
deployments** (**P-12**); operators are admin-provisioned with no self-serve reset;
every operator action is audited (**P-14**). The escalation path is designed not to
exist.

## R5 — KYC media exposure or loss
**Severity: High · Posture: Mitigated (was open).**
KYC documents on ephemeral dyno disk (an audit finding) risked loss and exposure.
**Mitigation:** durable S3/R2 object storage, versioned `CaseDocument`s pinned to
storage objects (**P-11**), accessed through audited paths, PII masked by audience
(commit #154). **Residual:** ongoing access-control and retention discipline as
volume grows.

## R6 — Async tier fails silently (worker down / broker outage)
**Severity: Medium · Posture: Mitigated.**
A dead worker or a Redis outage could strand effects.
**Mitigation:** the durable **outbox** means no event is lost — it drains when the
tier recovers (**P-9**); **worker heartbeats** make a dead worker visible
([Observability](../operations/52-observability.md)); the request path is hardened so a broker/
Channels outage degrades honestly rather than corrupting (commits #155–#157). Truth
is committed to Postgres before Celery is ever involved.
**Residual:** the audit-flagged **Celery-folded-into-web-dyno** compromise; the
tracked fix is independently scaled worker/beat services
([Infrastructure](../operations/50-infrastructure.md)).

## R7 — Postgres is the single point of failure
**Severity: High · Posture: Partially mitigated.**
Everything authoritative is in one Postgres (Neon). Its loss is the one truly
unrecoverable event.
**Mitigation:** nothing authoritative lives outside Postgres, so *only* Postgres
needs heroic durability; Neon backup/PITR; staging on a separate branch; projections
are rebuildable, so a projection incident is not a data incident.
**Residual:** HA/replica posture and tested restore drills must keep pace with volume;
this is the risk that most warrants continued operational investment.

## R8 — God modules erode the boundaries
**Severity: Medium · Posture: Partially mitigated.**
`contributions/services.py` (~2,000 lines) and `models.py` (~850) were flagged as god
modules; unchecked, they blur module boundaries.
**Mitigation:** internal split along sub-domain seams (the `services/`, `views/`
packages, [ADR-0013](../../adr/0013-contributions-module-split.md)); the dependency
rules (**Rule 1** especially) keep the ledger clean regardless of product-module size.
**Residual:** continued discipline; a future `import-linter` contract would mechanize
boundary enforcement ([Future Evolution](63-future-evolution.md)).

## R9 — CI gates are bypassed or rot
**Severity: High · Posture: Mitigated.**
The gates *are* the principles mechanized; disabling one silently repeals a rule.
**Mitigation:** gates are merge-blocking (**P-22**, E-7); the culture is "fix the
code, not the gate." **Residual:** vigilance that new dangerous patterns get *new*
guards (the grep-guard only catches known sins).

## R10 — No AML / financial-crime monitoring yet
**Severity: High (for regulated markets) · Posture: Open (Phase 8).**
Wepl currently lacks AML/velocity-based financial-crime monitoring.
**Mitigation path:** the single money door (**P-2**) is precisely the chokepoint
where such monitoring installs in *one* place; controls (Phase 3) already live there.
This is a *known, sequenced* gap (Phase 8), not an oversight — but it gates entry into
regulated markets and the treasury revenue line
([Business Model](../product/04-business-model.md)).

## R11 — Cross-tenant data leakage (as BaaS opens up)
**Severity: Critical (future) · Posture: Partially mitigated (pre-exposure).**
The defining risk of the BaaS endgame: one tenant reading or moving another's money.
**Mitigation:** the tenant boundary (**P-19**, [ADR-0008](../../adr/0008-multi-tenancy.md))
is built *before* the exposure, threaded through new code from the start.
**Residual:** Phase 7 must add exhaustive isolation testing and per-tenant API-key
scoping before any external traffic.

## R12 — Single-rail / single-market concentration
**Severity: Medium (strategic) · Posture: Mitigated (architecturally).**
Heavy dependence on M-Pesa and the Kenyan market is a business concentration risk.
**Mitigation:** the payment **port** (**P-18**) ensures the *market-entry* dependency
never became an *architectural* one — a new rail/market is an adapter, not a rewrite.
**Residual:** the business-level diversification is a go-to-market decision, not an
architectural blocker.

## R13 — Regulatory / licensing exposure
**Severity: High (strategic) · Posture: Open (design leaves room).**
Operating collective money — and especially treasury/float and BaaS — invites
regulatory obligations.
**Mitigation path:** compliance is a *design input* ([Philosophy §8](../product/02-philosophy.md)):
the ledger, identity ledger, and audit log exist partly to answer a regulator's
questions; no monetization line ships ahead of the controls that make it lawful
([Business Model](../product/04-business-model.md)). **Residual:** actual licensing is
a business/legal workstream (Phase 8 scope).

## R14 — Key-person / knowledge concentration
**Severity: Medium · Posture: Mitigated (by this handbook).**
A platform whose "why" lives only in founders' heads cannot outlast them — the exact
failure mode Wepl exists to cure for its *users* applies to the *team* too.
**Mitigation:** this handbook, the ADR corpus, and `CLAUDE.md` are the durable record
of intent, written for the engineer who joins three years from now
([Charter](../00-charter.md)). Documentation is a risk control.

---

## The risk posture, summarized

Wepl's most severe risks (R1, R2, R4) are **structurally mitigated** — held down by
machines (CI guards, boot guards, deployment separation) rather than by human
discipline, because human discipline is the thing that fails at 2 a.m. The open risks
(R10, R11, R13) are **known and sequenced** into Phases 7–8 rather than discovered
late. The residual operational risk that most warrants ongoing investment is **R7
(Postgres durability)** and the **R6 worker-separation** cleanup. None of the open
risks require relaxing a principle to address — which is the sign that the
architecture is sound.

---

*Continue to [Future Evolution](63-future-evolution.md).*
