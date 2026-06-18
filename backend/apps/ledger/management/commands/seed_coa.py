"""
Idempotently (re)seed the canonical Chart of Accounts.

    python manage.py seed_coa

Useful after creating a fresh database or when adding new GL accounts to
apps/ledger/coa.py. Safe to run any number of times.
"""
from django.core.management.base import BaseCommand

from apps.ledger.coa import seed_chart_of_accounts


class Command(BaseCommand):
    help = 'Seed the canonical GL accounts (Chart of Accounts).'

    def handle(self, *args, **options):
        accounts = seed_chart_of_accounts()
        for code, acct in sorted(accounts.items()):
            self.stdout.write(f"  {code}  {acct.type:<10} {acct.name}")
        self.stdout.write(self.style.SUCCESS(f"Chart of Accounts ready ({len(accounts)} GL accounts)."))
