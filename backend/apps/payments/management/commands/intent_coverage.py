"""Report PaymentIntent coverage over rail-backed FinancialTransactions.

    python manage.py intent_coverage              # summary
    python manage.py intent_coverage --sample 50  # more example rows
    python manage.py intent_coverage --strict     # exit non-zero unless ready

Read-only: reports, never writes or repairs. This answers the question ADR-0030
Slice A depends on — can PaymentIntent become authoritative for the rail
dimension, or is a backfill needed first? Intents are populated best-effort
(ADR-0014), so coverage must be measured rather than assumed.

The movements that should have an intent are found from the ledger (a journal
touching a settlement account), not from FT's ``mpesa_*`` columns — those are
written on the payout path only, so asking them would measure the one subset
that is covered by construction. See ``apps/payments/coverage.py``.
"""
from django.core.management.base import BaseCommand

from apps.payments.coverage import NEEDS_BACKFILL, NEEDS_REVIEW, READY, intent_coverage


class Command(BaseCommand):
    help = 'Report PaymentIntent coverage of rail-backed FinancialTransactions.'

    def add_arguments(self, parser):
        parser.add_argument('--sample', type=int, default=20,
                            help='How many example problem rows to show (default 20).')
        parser.add_argument('--strict', action='store_true',
                            help='Exit non-zero unless coverage is complete and agreeing.')

    def _rows(self, rows):
        for row in rows:
            self.stdout.write(
                f"  FT-{row['ft_id']} {row['op_type']}/{row['state']} "
                f"[{row['bucket']}] "
                f"conv={row['conversation_id'] or '-'} "
                f"receipt={row['receipt'] or row['receipt_hint'] or '-'}"
                + (f" -> intent {row['linkable_intent_id']}"
                   if row['linkable_intent_id'] else "")
            )

    def handle(self, *args, **options):
        r = intent_coverage(sample=options['sample'])

        if r['no_data']:
            self.stdout.write(self.style.WARNING(
                "No settlement-backed FinancialTransactions found — this database "
                "cannot answer the coverage question (empty dev DB, or the wrong "
                "target). Run it against staging/production data."))
            if options['strict']:
                raise SystemExit(1)
            return

        self.stdout.write(
            f"rail movements: {r['total_rail_backed']}  "
            f"covered: {r['covered']} ({r['coverage_pct']}%)  "
            f"uncovered: {r['uncovered']}  mismatched: {r['mismatched']}"
        )
        self.stdout.write(
            f"  linkable (intent exists, not linked): {r['linkable']}\n"
            f"  missing  (no intent anywhere):        {r['missing']}\n"
            f"  unattributable (needs triage):        {r['unattributable']}"
        )
        self.stdout.write(
            f"\nFT rail columns still populated: {r['legacy_rail_columns']}  "
            f"of which without an agreeing intent: {r['legacy_at_risk']}"
        )
        if r['legacy_at_risk']:
            self.stdout.write(self.style.WARNING(
                "  ^ dropping FT's mpesa_* columns would lose this rail data outright."))

        if r['gap']:
            self.stdout.write("\nuncovered by op_type: " + str(r['uncovered_by_op_type']))
            self.stdout.write("uncovered by state:   " + str(r['uncovered_by_state']))
            self.stdout.write("uncovered by bucket:  " + str(r['uncovered_by_bucket']))
            self.stdout.write("\nexamples (backfill needed):")
            self._rows(r['uncovered_sample'])

        if r['unattributable']:
            self.stdout.write(
                "\nexamples (money moved, no rail correlation — off-rail entry, "
                "or a payout still in flight):")
            self._rows(r['review_sample'])

        if r['mismatched']:
            self.stdout.write("\nexamples (intent disagrees with FT):")
            for row in r['mismatch_sample']:
                self.stdout.write(f"  FT-{row['ft_id']}: " + "; ".join(row['problems']))

        if r['verdict'] == READY:
            self.stdout.write(self.style.SUCCESS(
                "\nEvery rail movement has an agreeing PaymentIntent — no backfill "
                "needed for the Slice A cutover."))
            return

        if r['verdict'] == NEEDS_BACKFILL:
            self.stdout.write(self.style.WARNING(
                f"\nNOT ready: {r['linkable']} intent(s) need linking to their FT and "
                f"{r['missing']} need minting from rail records"
                + (f", plus {r['mismatched']} mismatch(es) to triage" if r['mismatched'] else "")
                + ", before PaymentIntent can be authoritative for the rail dimension."))
        elif r['verdict'] == NEEDS_REVIEW:
            self.stdout.write(self.style.WARNING(
                f"\nNOT ready: every correlated movement is covered, but "
                f"{r['unattributable']} movement(s) crossed the settlement boundary "
                "with no rail correlation. Confirm each is genuinely off-rail (a "
                "manual or cash posting) or still in flight before cutting over."))

        if options['strict']:
            raise SystemExit(1)
