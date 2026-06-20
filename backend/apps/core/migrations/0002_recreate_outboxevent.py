"""
Two parallel Phase 2 implementations merged (PR #18 + #19), leaving the outbox
migration (#18: UUID pk + `error`) inconsistent with the model/code that actually
runs on master (#19: BigAutoField pk + `last_error`). uuid->bigint cannot be
altered in place. The table is brand-new with no real data and nothing references
it, so drop and recreate it to match apps/core/models.OutboxEvent. The CreateModel
is generated into 0003 by makemigrations.
"""
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('core', '0001_outbox_event'),
    ]

    operations = [
        migrations.DeleteModel(name='OutboxEvent'),
    ]
