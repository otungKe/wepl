from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Replaces the UUID source_event_id field (PR #18) with a BigIntegerField
    event_id (PR #19) that matches OutboxEvent's auto-int PK and carries a
    unique constraint for at-least-once → effectively-once dedupe.
    """

    dependencies = [
        ('notifications', '0012_notification_source_event_id'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='notification',
            name='source_event_id',
        ),
        migrations.AddField(
            model_name='notification',
            name='event_id',
            field=models.BigIntegerField(blank=True, null=True, unique=True),
        ),
    ]
