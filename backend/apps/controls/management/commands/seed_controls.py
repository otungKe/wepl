"""Seed sensible default limit rules.

Idempotent: creates rules by name if missing. Tune them in /admin/ afterwards.

    python manage.py seed_controls
"""
from decimal import Decimal

from django.core.management.base import BaseCommand

from apps.controls.models import LimitRule

DEFAULTS = [
    # name, scope, direction, op_type, period, max_amount, max_count, action, priority
    ('Per-transaction payout cap',      'PER_USER', 'PAYOUT', '', 'TXN',   Decimal('150000'), None, 'DENY', 10),
    ('Daily payout cap (per user)',     'PER_USER', 'PAYOUT', '', 'DAY',   Decimal('300000'), None, 'DENY', 20),
    ('Payout velocity (per user/hour)', 'PER_USER', 'PAYOUT', '', 'HOUR',  None,              5,    'HOLD', 30),
    ('Daily pay-in cap (per user)',     'PER_USER', 'PAYIN',  '', 'DAY',   Decimal('500000'), None, 'DENY', 40),
]


class Command(BaseCommand):
    help = 'Create default limit rules if they do not already exist.'

    def handle(self, *args, **options):
        created = 0
        for name, scope, direction, op_type, period, max_amount, max_count, action, priority in DEFAULTS:
            _, was_created = LimitRule.objects.get_or_create(
                name=name,
                defaults=dict(
                    scope=scope, direction=direction, op_type=op_type, period=period,
                    max_amount=max_amount, max_count=max_count, action=action, priority=priority,
                ),
            )
            created += int(was_created)
            self.stdout.write(('  + ' if was_created else '  · ') + name)
        self.stdout.write(self.style.SUCCESS(f"seed_controls: {created} rule(s) created, {len(DEFAULTS) - created} already present."))
