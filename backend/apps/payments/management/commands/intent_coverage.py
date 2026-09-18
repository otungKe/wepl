"""Report PaymentIntent coverage over rail-backed FinancialTransactions.

    python manage.py intent_coverage              # summary
    python manage.py intent_coverage --sample 50  # more example rows
    python manage.py intent_coverage --strict     # exit non-zero unless ready

Read-only: reports, never writes or repairs. This answers the question ADR-0030
Slice A depends on — can PaymentIntent become authoritative for the rail
dimension, or is a backfill needed first? Intents are populated best-effort
(ADR-0014), so coverage must be measured rather than assumed.
"""
from django.core.management.base import BaseCommand

from apps.payments.coverage import intent_coverage


class Command(BaseCommand):
    help = 'Report PaymentIntent coverage of rail-backed FinancialTransactions.'

    def add_arguments(self, parser):
        parser.add_argument('--sample', type=int, default=20,
                            help='How many example problem rows to show (default 20).')
        parser.add_argument('--strict', action='store_true',
                            help='Exit non-zero unless coverage is complete and agreeing.')

    def handle(self, *args, **options):
        r = intent_coverage(sample=options['sample'])

        if r['no_data']:
            self.stdout.write(self.style.WARNING(
                "No rail-backed FinancialTransactions found — this database cannot "
                "answer the coverage question (empty dev DB, or the wrong target). "
                "Run it against staging/production data."))
            if options['strict']:
                raise SystemExit(1)
            return

        self.stdout.write(
            f"rail-backed FTs: {r['total_rail_backed']}  "
            f"covered: {r['covered']} ({r['coverage_pct']}%)  "
            f"uncovered: {r['uncovered']}  mismatched: {r['mismatched']}"
        )

        if r['uncovered']:
            self.stdout.write("\nuncovered by op_type: " + str(r['uncovered_by_op_type']))
            self.stdout.write("uncovered by state:   " + str(r['uncovered_by_state']))
            self.stdout.write("\nexamples (no PaymentIntent):")
            for row in r['uncovered_sample']:
                self.stdout.write(
                    f"  FT-{row['ft_id']} {row['op_type']}/{row['state']} "
                    f"conv={row['conversation_id'] or '-'} "
                    f"checkout={row['checkout_id'] or '-'} "
                    f"receipt={row['receipt'] or '-'}"
                )

        if r['mismatched']:
            self.stdout.write("\nexamples (intent disagrees with FT):")
            for row in r['mismatch_sample']:
                self.stdout.write(f"  FT-{row['ft_id']}: " + "; ".join(row['problems']))

        if r['ready_for_cutover']:
            self.stdout.write(self.style.SUCCESS(
                "\nPaymentIntent covers every rail-backed FT and agrees with it — "
                "no backfill needed for the Slice A cutover."))
        else:
            self.stdout.write(self.style.WARNING(
                "\nNOT ready: a backfill (and/or mismatch triage) is needed before "
                "PaymentIntent can be authoritative for the rail dimension."))
            if options['strict']:
                raise SystemExit(1)
