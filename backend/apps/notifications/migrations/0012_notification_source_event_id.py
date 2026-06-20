import uuid

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0011_notificationpreferences'),
        ('core',          '0001_outbox_event'),
    ]

    operations = [
        migrations.AddField(
            model_name='notification',
            name='source_event_id',
            field=models.UUIDField(blank=True, db_index=True, null=True),
        ),
    ]
