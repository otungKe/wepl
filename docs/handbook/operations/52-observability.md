# Operations / 52 — Observability

> How we know what the system is doing — and, in a money platform, how we *prove*
> what it did. Observability here has two faces: the ordinary operational one
> (errors, latency, health) and a financial one unique to Wepl — **the ledger is
> itself the ultimate observability tool**, because it is an immutable, provable
> record of every movement.

Grounded in [ADR-0020](../../adr/0020-observability-standard.md); Sentry for
errors; the ledger, audit log, and outbox for financial and action observability.

---

## Two kinds of observability

| Kind | Question it answers | Where it lives |
|------|--------------------|-----------------|
| **Operational** | Is the system healthy? Fast? Erroring? | Sentry, logs, health checks, worker heartbeats |
| **Financial / forensic** | What happened to this money? Who did this? Does it all balance? | The ledger, the audit log, the case timeline, the outbox |

Most platforms only have the first. Wepl's second kind is a direct dividend of the
[immutable-log design](../architecture/24-data-architecture.md): because truth is
append-only, the system can always answer "what happened and when" without
reconstruction.

## Operational observability

### Errors — Sentry (ADR-0020)
Sentry captures exceptions across the API tier and workers, with release tagging so
an error is tied to the deploy that introduced it. It is the first line for "what
broke." The observability standard (ADR-0020) defines the conventions — structured
context, sensitive-data hygiene (never log OTPs, tokens, or full KYC data; the
counterparty-name masking of commit #154 is the model — full for ops, masked for
members).

### Logs
Structured logs across request and worker paths. In production, `SMS_BACKEND=console`
routes real OTP codes to logs (retrievable operationally, not sent over an
unconfigured SMS path) — an example of logging as a deliberate operational channel.
Degradation decisions (a `503` on OTP under cache outage, a fail-open throttle) are
logged so an operator can see *why* the system behaved as it did (**P-16**).

### Health & worker heartbeats
The API exposes health; workers report liveness (a `WorkerHeartbeat`, migration
`core.0004`) so a silently-dead worker — the classic async failure — is *visible*
rather than discovered when a queue backs up. This directly addresses the
[failure domain](../architecture/20-system-architecture.md) where a worker dies but
the web tier looks healthy.

### Queue and outbox depth
Because delivery is asynchronous and at-least-once, the **outbox backlog** and Celery
queue depths are key signals: a growing undelivered-event backlog means effects are
lagging (even though truth is fine). Watching outbox depth is how we see delivery
health separately from money health.

## Financial observability — the ledger as the ultimate tool

### The trial balance is a continuous health metric
`reconcile_ledger` proves Σdebit == Σcredit globally (**P-6**), in CI *and in
production*. A non-zero trial balance is the single most important financial alarm
Wepl has — it means the impossible happened, and it is caught rather than
discovered. The DB-level deferred trigger makes an unbalanced commit impossible in
the first place; reconciliation is the belt to the trigger's braces.

### Every shilling is traceable
Any money question — "where did this payment go," "what is this member owed," "what
does the pool hold" — is answered by *reading immutable journal lines*, grouped into
human-legible **Financial Transactions** with a searchable reference and
counterparty ([Financial Architecture](../domain/12-financial-architecture.md),
ADR-0025). The transactions registry (inquiry-first, filterable by
date/amount/account/fund, commits #148–#149) is the operator's forensic lens.

### Suspense is a monitored queue
Ambiguous inbound money in `1100` Suspense
([Payments](../architecture/27-payments-architecture.md)) is a *visible, monitored*
reconciliation queue — never a silent drop. A growing suspense balance is an
operational signal that a rail integration or a reconciliation path needs attention.

### Every operator action is observable and non-repudiable
The append-only `AuditEvent` log (**P-14**, [ADR-0019](../../adr/0019-append-only-audit-log.md))
means "who did this?" is always answerable. Operator observability is not a separate
logging system — it is the same immutable-record discipline as the ledger, applied
to actions.

### Identity is observable too
The `CaseEvent` timeline ([Identity](../domain/14-identity-architecture.md)) makes
every KYC journey fully reconstructable — what evidence, what decision, by whom, when
— which is exactly what a regulator (Phase 8) will ask for.

## Alerting priorities

In rough order of severity, the signals that should page:

1. **Non-zero trial balance** — a financial-integrity breach. Highest priority.
2. **Production boot refused** or repeated crash — likely the OTP-bypass guard or a
   config error (fail-closed working as designed, but needs a human).
3. **Rising suspense balance** — money arriving that cannot be matched.
4. **Outbox/queue backlog growth** — effects lagging; investigate the worker/broker.
5. **Error-rate / latency spikes** (Sentry) — ordinary operational health.
6. **Worker heartbeat lost** — a dead async tier.

The ordering reflects the platform's values: **financial integrity first, honest
availability second, ordinary performance third.**

## Privacy and sensitive-data hygiene in telemetry

- **Never log secrets or credentials** — OTPs, tokens, passwords, full card/rail
  secrets.
- **Mask PII by audience** — the counterparty-name masking (full for ops, masked for
  members, commit #154) is the pattern: observability must not become a PII leak.
- **KYC data stays out of general telemetry** — it lives in the case system and
  object storage, accessed through audited paths, not scattered into logs.

## The observability thesis

Wepl can always answer *what happened to the money* and *who did what*, because those
answers are not reconstructed from telemetry — they are read from immutable records
that exist as a first principle of the design. Operational observability tells us the
system is healthy; the ledger and audit log let us *prove* it was correct. Both
matter; only Wepl's design gives the second for free.

---

*Continue to [Operational & Scalability Strategy](53-operations-and-scalability.md).*
