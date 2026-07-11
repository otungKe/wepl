# Product / 02 — Philosophy

> The beliefs about people, money, and software that shape every Wepl decision.
> Principles ([03](03-principles.md)) are the rules; this is the *why* underneath
> them. When a rule seems to get in the way, re-read this before bending it.

---

## 1. Trust is the product; the features are packaging

People do not adopt a chama app because it has nicer buttons than a notebook. They
adopt it — and, crucially, *keep* their money in it — because it is **more
trustworthy than the alternatives**, which are a person's honesty and a group's
fading memory.

Everything Wepl does is in service of manufacturing trust that used to require a
trusted individual. The double-entry ledger, the immutable audit trail, the
governance that enforces rather than records, the identity-as-a-ledger — these are
not "enterprise" indulgences. They are the product. A feature that adds
convenience at the cost of provability is a bad trade, because it erodes the one
thing we are actually selling.

**Consequence:** when convenience and provability conflict, provability wins, and
we work to make the provable thing also convenient — rather than making the
convenient thing merely *look* provable.

## 2. Money must be conserved, and conservation must be *provable*

Money does not appear or vanish; it moves. A system of record for money that
cannot *prove* conservation is not trustworthy — it is merely confident. This is
why Wepl is double-entry to its core: for every movement, something is debited and
something is credited, and the sum is always zero. The trial balance is not a
report we run occasionally; it is an invariant the system defends continuously,
including at the database level.

This belief has a sharp corollary the platform learned the hard way: **you cannot
have two sources of truth for money.** An earlier Wepl tracked balances in three
places — mutable columns, a single-entry shadow, and a dormant double-entry core —
and spent effort *detecting* the drift between them. Drift between two "truths" is
not a bug to be fixed once; it is the guaranteed steady state of any system that
allows it. So there is exactly one book of record, and everything else is a cache
derived from it. See [ADR-0001](../../adr/0001-ledger-first-double-entry.md) and
[ADR-0002](../../adr/0002-remove-legacy-ledger-and-mutable-balances.md).

## 3. The immutable core, the disposable shell

The most durable design idea in Wepl, applied over and over: **make the source of
truth an append-only sequence of immutable events, and make everything a user
reads a projection you can throw away and rebuild.**

- Money: immutable journal lines → derived `AccountBalance` projection.
- Identity: immutable `CaseEvent` timeline → derived `KYCProfile.status`.
- Operator actions: append-only `AuditEvent` log.
- Domain events: append-only `OutboxEvent` rows.

Immutable truth cannot be quietly corrupted; projections can be corrupted but are
*disposable*, so corruption is a rebuild, not a disaster. This is the same insight
in four places, and its recurrence is not coincidence — it is the platform's
signature move. When you design something new that holds important truth, ask:
*what is the immutable log, and what is the disposable projection?*

## 4. One door per concern

For each cross-cutting concern there should be exactly **one** place it happens, so
there is exactly one place to reason about it, secure it, and extend it.

- All money moves through `post_journal()`.
- All KYC decisions go through `verification.service.decide()`.
- All domain events are announced through `emit()`.
- All payment rails are reached through the `PaymentProvider` port.
- All operator actions are authorised through `RequireCapability` and recorded
  through `record_action()`.

A single door is a single place to add a limit, a risk check, an audit hook, a new
currency. A system with many doors for the same concern is a system where the next
requirement has to be implemented — and can be forgotten — in many places. The
narrowness of these doors is deliberate and defended (CI fails if money is moved
any other way).

## 5. Additive before destructive

Changing money infrastructure is heart surgery on a beating heart. The platform's
method, proven through the Phase 0 cutover, is: **build the new path, dual-write,
verify equivalence under a green test suite, and only then delete the old path.**
Never delete working money code on faith. Every change is reversible at the VCS
level, and every change that touches money is guarded by tests that must be green.

## 6. Serve the collective, design for the individual's confidence

The customer is the group, but the *experience* is had by one person at a time,
often with low financial confidence and on a mid-range Android phone over patchy
data. So:

- **Legibility over density.** A member should understand, at a glance, what they
  are owed and what the pool holds. If they have to interpret, we have failed.
- **Reassurance over cleverness.** Money moments (paying in, a payout, a failed
  transaction) are anxious moments. The product's job is to reduce anxiety with
  clarity and honest status, not to delight with novelty.
- **The software should disappear.** The best outcome is that the group stops
  thinking about the tool and simply trusts that the money is right.

See [UX Philosophy](06-ux-and-design.md).

## 7. Honest software

The system tells the truth about its own state — to users and to operators.

- A failed payment says it failed; it never optimistically implies success.
- When a dependency is down, the system **degrades cleanly and legibly** rather
  than pretending or failing opaquely. (The auth path, for instance, is designed
  so a cache outage yields an honest `503` for OTP and a fail-*open* PIN path
  rather than a silent lie — recent hardening work, commits #155–#157.)
- Operators can always reconstruct *what happened and who did it* from immutable
  logs.

Dishonest software — software that hides its failures — is disqualifying in a
financial product, because it converts a recoverable error into a breach of trust.

## 8. Regulation is a design input, not an afterthought

Wepl is on a path to becoming regulated financial infrastructure. Compliance
(AML, KYC tiers, auditability, data residency) is threaded into the architecture
from the start as *capabilities the design leaves room for*, even before they are
built. The ledger, the identity ledger, and the audit log exist in part because a
regulator will one day ask questions only they can answer. We leave the doors open
without paying to furnish every room today (roadmap sequencing rationale).

## 9. Boring where it counts, novel only where it earns its keep

A financial core is the wrong place to be clever. We choose mature, well-understood
technology (Django, Postgres, double-entry accounting invented centuries ago) for
the parts that must not surprise us, and reserve novelty for genuine product
differentiation. Cleverness is a cost paid in every future engineer's
comprehension; we spend it deliberately. See
[Engineering Principles](../engineering/30-engineering-principles.md).

---

## The philosophy, compressed

> Sell trust, not features. Conserve money and *prove* it. Keep the truth
> immutable and the projections disposable. Give each concern exactly one door.
> Build additively, tell the truth about failure, leave room for the regulator,
> and be boring in the core so you can be excellent at the edge.

---

*Continue to [Core Principles](03-principles.md).*
