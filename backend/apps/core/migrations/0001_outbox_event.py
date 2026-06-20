import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name='OutboxEvent',
            fields=[
                ('id',           models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ('event_type',   models.CharField(db_index=True, max_length=100)),
                ('payload',      models.JSONField()),
                ('status',       models.CharField(
                    choices=[
                        ('pending',     'Pending'),
                        ('processing',  'Processing'),
                        ('delivered',   'Delivered'),
                        ('dead_letter', 'Dead Letter'),
                    ],
                    db_index=True, default='pending', max_length=15,
                )),
                ('attempts',     models.PositiveSmallIntegerField(default=0)),
                ('error',        models.TextField(blank=True)),
                ('created_at',   models.DateTimeField(auto_now_add=True, db_index=True)),
                ('processed_at', models.DateTimeField(blank=True, null=True)),
            ],
            options={
                'verbose_name':        'Outbox Event',
                'verbose_name_plural': 'Outbox Events',
                'ordering': ['created_at'],
            },
        ),
        migrations.AddIndex(
            model_name='outboxevent',
            index=models.Index(fields=['status', 'created_at'], name='outbox_status_created_idx'),
        ),
    ]
