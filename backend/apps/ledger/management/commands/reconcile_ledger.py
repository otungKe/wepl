"""
Run the ledger integrity reconciliation on demand.

    python manage.py reconcile_ledger            # report + auto-repair drift
    python manage.py reconcile_ledger --no-repair # report only

Checks that the global trial balance is zero and that every AccountBalance
projection matches a replay of its immutable journal lines. Exits non-zero if the
books are unbalanced or (with --no-repair) drift is found, so it is usable as a
deploy/cron health gate.
"""
from django.core.management.base import BaseCommand

from apps.ledger.tasks import reconcile_ledger


class Command(BaseCommand):
    help = 'Reconcile the ledger (trial balance zero + projection == replay).'

    def add_arguments(self, parser):
        parser.add_argument(
            '--no-repair', action='store_true',
            help='Report drift without repairing the projection.',
        )

    def handle(self, *args, **options):
        repair = not options['no_repair']
        report = reconcile_ledger(repair=repair)

        self.stdout.write(
            f"trial balance: debit={report['total_debit']} "
            f"credit={report['total_credit']} balanced={report['balanced']}"
        )
        self.stdout.write(f"projection drift: {report['drift_count']} account(s) "
                          f"(repaired={report['repaired']})")

        failed = (not report['balanced']) or (report['drift_count'] and not repair)
        if failed:
            self.stderr.write(self.style.ERROR("Ledger reconciliation FAILED."))
            raise SystemExit(1)
        self.stdout.write(self.style.SUCCESS("Ledger reconciliation OK."))
