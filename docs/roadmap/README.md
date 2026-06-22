# WEPL — Financial OS Roadmap

> Source of truth for how WEPL evolves from a community-finance application into a
> ledger-first Financial Operating System. This directory is versioned with the
> code. Every phase is mirrored as a GitHub issue (see **Tracking** below) so
> progress is auditable from both the repo and the GitHub board.

---

## 1. Where we are

Per the architecture audit ([`../audit/2026-06-architecture-audit.md`](../audit/2026-06-architecture-audit.md)),
WEPL is a well-engineered **Stage 2→3 community-finance application** with a
correctly-designed but **dormant** double-entry core. Money today is tracked in
**three** places, and the authoritative one is the weakest:

1. **Mutable balance columns** — `Contribution.current_amount`, `WelfareFund.balance`,
   `SharesFund.total_pool`, `ContributionAccount`, `ContributionBalance` (what the
   business logic actually reads and gates on).
2. **Legacy single-entry ledger** — `LedgerEntry` + `apps/ledger/writer.py` +
   `apps/ledger/queries.py` (a reconciled shadow).
3. **Double-entry core** — `Account` / `JournalEntry` / `JournalLine` /
   `AccountBalance` (`apps/ledger/posting.py`, `coa.py`, `balances.py`). Correct,
   tested, and wired to **nothing** outside `apps/ledger/`.

The roadmap's central act is to make **(3) the single book of record** and delete
**(1)** and **(2)**.

## 2. Target

A ledger-first Financial OS where **`post_journal()` is the only door money walks
through**, so every cross-cutting concern (limits, risk, AML, audit, multi-currency,
settlement, reporting) has exactly one insertion point.

## 3. Guiding principles

- **One book of record.** Balances are *derived* from immutable journal lines.
  Mutable balance fields, if they survive at all, are caches rebuilt from the ledger.
- **One money door.** All value movement goes through `post_journal()`.
- **Additive before destructive.** Dual-write and verify before deleting.
- **Every change is reversible at the VCS level and, where it touches money,
  guarded by a green test suite.**
- **Decisions are recorded.** Anything structural gets an ADR in [`../adr/`](../adr/).

---

## 4. Phases

| # | Phase | Goal | Stage reached | Epic | Status |
|---|-------|------|---------------|------|--------|
| 0 | [Ledger-First Cutover (Legacy Wipe)](PHASE-0-ledger-cutover.md) | Make double-entry authoritative; delete all legacy money code | 3 (solid) | [#4](https://github.com/otungKe/wepl/issues/4) | 🟢 Done (P0-01 → P0-09) |
| 1 | [Payment Rail Abstraction](PHASE-1-payment-rails.md) | `PaymentProvider` port; M-Pesa as adapter #1 | 3→4 | [#5](https://github.com/otungKe/wepl/issues/5) | 🟢 Done |
| 2 | [Durable Eventing (Transactional Outbox)](PHASE-2-eventing-outbox.md) | No lost domain events | 4 | [#6](https://github.com/otungKe/wepl/issues/6) | 🟢 Done |
| 3 | [Controls: Limits & Risk](PHASE-3-controls-limits-risk.md) | Limits + velocity/fraud gate at the posting chokepoint | 4 | [#7](https://github.com/otungKe/wepl/issues/7) | 🟢 Done (core; P3-01→05) |
| 4 | [Reporting & GL](PHASE-4-reporting-gl.md) | Trial balance, statements, audit exports | 4 | [#8](https://github.com/otungKe/wepl/issues/8) | 🟢 Done (core; P4-01→04) |
| 5 | [Multi-Currency](PHASE-5-multi-currency.md) | FX-aware Money; per-currency balancing | 4→5 | [#9](https://github.com/otungKe/wepl/issues/9) | 🔴 Not started |
| 6 | [Multi-Tenancy](PHASE-6-multi-tenancy.md) | Tenant boundary + isolation | 5 | [#10](https://github.com/otungKe/wepl/issues/10) | 🔴 Not started |
| 7 | [Banking-as-a-Service](PHASE-7-baas.md) | Public API, webhooks-out, sandbox, API keys | 5 | [#11](https://github.com/otungKe/wepl/issues/11) | 🔴 Not started |
| 8 | [Enterprise & Compliance](PHASE-8-enterprise-compliance.md) | AML, monitoring, treasury, data residency | 6 | [#12](https://github.com/otungKe/wepl/issues/12) | 🔴 Not started |

**Sequencing rationale:** Phases 1–4 only become cheap *after* the posting
chokepoint exists (Phase 0). Phases 5–8 are deliberately deferred — building them
on a mutable-field core would be pouring the second floor before the foundation.
Currency/tenant *awareness* is threaded into new code from Phase 0 so the doors
are left open without paying for the rooms yet.

---

## 5. Status legend

| Symbol | Meaning |
|--------|---------|
| 🔴 | Not started |
| 🟡 | In progress |
| 🟢 | Done (acceptance criteria met + merged) |
| ⏸️ | Blocked (see note) |
| 🧪 | In verification / awaiting CI |

## 6. Work-item ID convention

`P{phase}-{nn}` — e.g. `P0-05`. IDs are stable and referenced by commits
(`P0-05: rewire contribute() to post_journal`), the phase docs, and GitHub issues.

## 7. Tracking (in-repo + GitHub)

- **Source of truth:** these Markdown docs.
- **Board:** each phase has a GitHub *epic* issue containing its work-item
  checklist; the master tracking issue links them all. Issue links are recorded in
  the table below once created.
- **Definition of Done (every work item):** code merged · acceptance criteria met ·
  tests green in CI · docs/ADR updated · checkbox ticked in both the phase doc and
  the GitHub epic.

| Artifact | Link |
|----------|------|
| Master tracking issue | [#13](https://github.com/otungKe/wepl/issues/13) |
| Phase epics | [#4](https://github.com/otungKe/wepl/issues/4) (P0) · [#5](https://github.com/otungKe/wepl/issues/5) (P1) · [#6](https://github.com/otungKe/wepl/issues/6) (P2) · [#7](https://github.com/otungKe/wepl/issues/7) (P3) · [#8](https://github.com/otungKe/wepl/issues/8) (P4) · [#9](https://github.com/otungKe/wepl/issues/9) (P5) · [#10](https://github.com/otungKe/wepl/issues/10) (P6) · [#11](https://github.com/otungKe/wepl/issues/11) (P7) · [#12](https://github.com/otungKe/wepl/issues/12) (P8) |

## 8. Definition of Done for the whole roadmap

WEPL is a "true Financial OS" when: (a) the double-entry ledger is the only source
of monetary truth; (b) `post_journal()` is the sole money mutation path and carries
limits/risk/audit hooks; (c) a global trial balance is provably zero in CI and in
production reconciliation; (d) a new payment rail or currency can be added without
touching financial logic; and (e) financial statements are generated directly from
the GL.
