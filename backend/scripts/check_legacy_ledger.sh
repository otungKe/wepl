#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# P0-07 guard — legacy single-entry ledger & mutable balance caches stay deleted.
#
# Money moves only via post_journal() and balances are derived from immutable
# journal lines (ADR-0002/ADR-0003). This check fails the build if the deleted
# pre-ledger constructs are reintroduced.
#
# Run from anywhere:  backend/scripts/check_legacy_ledger.sh
# CI runs the same script, so there is one copy of the pattern.
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

cd "$(dirname "$0")/.."

pattern='LedgerEntry|write_ledger_entry|write_reversal_credit|ledger\.queries'
pattern="$pattern|ContributionAccount|ContributionBalance"
pattern="$pattern|current_amount[[:space:]]*=[[:space:]]*F\(|total_pool[[:space:]]*=[[:space:]]*F\(|balance[[:space:]]*=[[:space:]]*F\('balance'\)"
# ShareHolding kept the same kind of counter until it was derived from
# the shares sub-ledger; it drifted precisely because this guard named
# symbols rather than the rule and never looked at it.
pattern="$pattern|shares_count[[:space:]]*=[[:space:]]*F\(|total_contributed[[:space:]]*=[[:space:]]*F\("
# The legacy contribution-coupled payments.Payment (a money record kept
# OUTSIDE the ledger, pre-ADR-0003 precision) and its serializer/view were
# removed (#165) — don't let them come back. Word boundaries keep this off
# the legitimate PaymentIntent (ADR-0014) and ContributionPaymentSerializer.
pattern="$pattern|class Payment\(|\bPaymentSerializer\b|\bContributionPaymentsView\b"

if grep -rEn "$pattern" apps --include=*.py \
     | grep -vE "/migrations/|/tests\.py|/tests_"; then
  echo "::error::Legacy ledger / mutable balance cache / payments.Payment reintroduced — money moves only via post_journal() and balances are ledger-derived; external payments use payments.PaymentIntent (ADR-0014)."
  exit 1
fi

echo "P0-07 guard: clean."
