"""Report PaymentIntent coverage over rail-backed FinancialTransactions.

    python manage.py intent_coverage              # summary
    python manage.py intent_coverage --sample 50  # more example rows
    python manage.py intent_coverage --strict     # exit non-zero unless ready

Read-only: reports, never writes or repairs. The payout side is covered by
construction (the dispatch mints an intent before calling the rail); what this
measures is the collection gap — the STK chokepoint mints its intent with no
financial_transaction, and the paybill path mints none at all.

The movements that should have an intent are found from the ledger (a journal
touching a settlement account), which is the only evidence there is: FT carries
no rail columns (ADR-0030). See ``apps/payments/coverage.py``.
"""
from django.core.management.base import BaseCommand

from apps.payments.coverage import NEEDS_BACKFILL, NEEDS_REVIEW, READY, intent_coverage


class Command(BaseCommand):
    help = 'Report PaymentIntent coverage of rail-backed FinancialTransactions.'

    def add_arguments(self, parser):
        parser.add_argument('--sample', type=int, default=20,
                            help='How many example problem rows to show (default 20).')
        parser.add_argument('--strict', action='store_true',
                            help='Exit non-zero unless every rail movement has an intent.')

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
            f"uncovered: {r['uncovered']}"
        )
        self.stdout.write(
            f"  linkable (intent exists, not linked): {r['linkable']}\n"
            f"  missing  (no intent anywhere):        {r['missing']}\n"
            f"  unattributable (needs triage):        {r['unattributable']}"
        )
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

        if r['verdict'] == READY:
            self.stdout.write(self.style.SUCCESS(
                "\nEvery rail movement has a PaymentIntent — no backfill needed."))
            return

        if r['verdict'] == NEEDS_BACKFILL:
            self.stdout.write(self.style.WARNING(
                f"\nNOT ready: {r['linkable']} intent(s) need linking to their FT and "
                f"{r['missing']} need minting from rail records, before every rail "
                "movement is represented by an intent."))
        elif r['verdict'] == NEEDS_REVIEW:
            self.stdout.write(self.style.WARNING(
                f"\nNOT ready: every correlated movement is covered, but "
                f"{r['unattributable']} movement(s) crossed the settlement boundary "
                "with no rail correlation. Confirm each is genuinely off-rail (a "
                "manual or cash posting) or still in flight before cutting over."))

        if options['strict']:
            raise SystemExit(1)
