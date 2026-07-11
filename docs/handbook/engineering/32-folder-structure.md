# Engineering / 32 — Folder Structure

> Where things live and why. The layout mirrors the [domain](../domain/10-domain-model.md)
> and the [module boundaries](../architecture/22-module-boundaries.md): one Django
> app per bounded context, a conventional internal shape per app, and settings
> layered by environment. A predictable layout means an engineer can find the right
> file from the domain word alone.

---

## Top level

```
wepl/
├── backend/            # the Django Financial-OS backend — nearly all work happens here
├── mobile/             # Expo / React Native member app
├── web/                # Next.js member web app
├── backoffice/         # ops console frontend (separate deployment, P-12)
├── docs/               # the source of truth for intent
│   ├── handbook/       # THIS handbook — the constitution
│   ├── adr/            # Architecture Decision Records (immutable case law)
│   ├── roadmap/        # phased plan (PHASE-0 … PHASE-8)
│   ├── audit/          # captured architecture audits
│   └── review/         # hardening reviews
├── render.yaml         # deployment blueprint (Render + Neon)
├── docker-compose.yml  # full local stack
└── CLAUDE.md           # working instructions for engineers/agents
```

**Rule:** intent lives in `docs/`; the code implements it. When code and `docs/`
disagree, that is a defect to resolve ([Charter](../00-charter.md)), not a tolerated
difference.

## Backend layout

```
backend/
├── config/
│   └── settings/
│       ├── base.py         # shared settings
│       ├── development.py  # default; local + CI
│       └── production.py   # prod hardening (incl. the OTP-bypass boot guard, P-15)
├── apps/                   # one app per bounded context
│   ├── ledger/             # THE BOOK OF RECORD — depends on nothing above it
│   ├── core/               # event bus + transactional outbox + shared exceptions
│   ├── tenants/            # multi-tenant isolation boundary
│   ├── audit/              # append-only operator audit log
│   ├── payments/           # PaymentProvider port + registry
│   ├── mpesa/              # Daraja adapter guts (reached only via the port)
│   ├── users/              # customer identity: phone auth, OTP, sessions, KYC tiers, OCR
│   ├── verification/       # identity-as-a-ledger: cases, events, documents
│   ├── backoffice/         # staff identity + ops console (/api/ops/*)
│   ├── communities/        # communities, membership, roles, governance
│   ├── contributions/      # the money products (contributions/welfare/shares/advances)
│   ├── controls/           # limits & risk at the posting chokepoint
│   ├── conversations/      # group chat (Channels)
│   ├── notifications/      # multi-channel delivery (SMS/email/push)
│   ├── activity/           # activity feeds
│   ├── reminders/          # scheduled reminders
│   ├── files/              # media/document storage pipeline
│   └── search/             # search indexing/query
├── manage.py
├── requirements.txt        # pinned dependencies
├── .python-version         # pins Python 3.12 so Render can't drift from CI
└── start.sh                # prod start command
```

The app list *is* the domain map. If you cannot tell which app a change belongs in,
re-read [Module Boundaries](../architecture/22-module-boundaries.md) — the answer is
almost always "the app that *owns* the model being changed."

## The anatomy of an app

Django apps follow a conventional internal shape. Larger apps split behaviour and
views into packages rather than single files.

```
apps/<name>/
├── __init__.py
├── apps.py             # AppConfig — event consumers registered here in ready()
├── models.py           # state + invariants (or models/ package if large)
├── services.py         # behaviour (or services/ package — see contributions)
├── views.py            # thin HTTP layer (or views/ package)
├── serializers.py      # DRF serializers
├── urls.py             # routes
├── permissions.py      # authz hooks into the centralized policy
├── policies.py         # domain policy (where applicable)
├── tasks.py            # Celery tasks
├── admin.py            # Django admin (django-unfold)
├── migrations/         # schema + data migrations (incl. invariant triggers)
└── tests.py / tests_*.py   # both are discovered
```

### The ledger app — the reference implementation
`apps/ledger/` is worth knowing by heart, because its file names *are* the money
architecture ([Financial Architecture](../domain/12-financial-architecture.md)):

| File | Owns |
|------|------|
| `posting.py` | `post_journal()` — the one money door |
| `posting_map.py` | canonical debit/credit recipes |
| `coa.py` | chart of accounts + account resolution |
| `money.py` | the `Money` value object |
| `balances.py` | the `AccountBalance` projection |
| `models.py` | `FinancialTransaction`, `JournalEntry`, `JournalLine`, `Account`, `AccountBalance`, `ExchangeRate` |
| `reporting.py` | trial balance, statements (Phase 4) |
| `fx.py` | multi-currency / FX (Phase 5) |
| `reconcile` (management) | `reconcile_ledger` — proves the trial balance is zero |
| `tests_*.py` | posting map, reconcile, reporting, money, fx |

## Settings layering

`base.py` → `development.py` / `production.py`. Development is the default (local +
CI); production adds hardening — most importantly the **boot-time OTP-bypass guard**
(**P-15**) and the `DATABASE_URL`/Neon handling with `CONN_HEALTH_CHECKS`. Never put
a production-only guard in `base.py` where development could disable it, and never
put a development convenience where production could inherit it.

## Where a new thing goes — a decision guide

- **A new money product** (e.g. a new kind of fund) → inside `contributions`, split
  along a sub-domain seam; it *calls* the ledger, never edits it.
- **A new payment rail** → a new adapter behind the `payments` port; its guts in
  their own module like `mpesa/` (**P-17/P-18**).
- **A new identity check** → a new adapter behind the `users/identity` port
  (**P-17**).
- **A new cross-module reaction** → a consumer registered in an app's
  `AppConfig.ready()`, driven by an `emit()`-ted event (E-14).
- **A new operator capability** → the capability map in `backoffice`.
- **A new structural decision** → an ADR in `docs/adr/`, then a handbook revision
  (**P-20**).

If a change seems to require editing `ledger` to add a *product* feature, the design
is wrong — the ledger depends on nothing above it
([Module Boundaries Rule 1](../architecture/22-module-boundaries.md)).

---

*Continue to [Testing Strategy](33-testing-strategy.md).*
