"""
Add next_run_at + last_executed_at to StandingOrder.

next_run_at  — the datetime when this order is next eligible to execute.
               The Celery task filters on next_run_at__lte=now() so only
               due orders fire (fixes the "every order every run" bug).

last_executed_at — the datetime of the most recent successful execution
                   (informational / auditing).

Data migration: set next_run_at = NOW() for all existing active orders so
they are considered due on the next scheduled task run (consistent with the
old behaviour of always running when active).
"""
from django.db import migrations, models
from django.utils import timezone


def set_initial_next_run_at(apps, schema_editor):
    StandingOrder = apps.get_model('contributions', 'StandingOrder')
    now = timezone.now()
    StandingOrder.objects.filter(is_active=True, next_run_at__isnull=True).update(next_run_at=now)


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0012_contributiontransaction_mpesa_receipt'),
    ]

    operations = [
        migrations.AddField(
            model_name='standingorder',
            name='next_run_at',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AddField(
            model_name='standingorder',
            name='last_executed_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(set_initial_next_run_at, migrations.RunPython.noop),
    ]
