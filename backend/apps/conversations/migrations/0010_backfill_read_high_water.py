from django.db import migrations


def backfill_high_water(apps, schema_editor):
    """Set last_read_message_id from the existing last_read_at timestamp so
    unread counts stay correct after the high-water-mark switch (ADR-0012)."""
    schema_editor.execute(
        """
        UPDATE conversations_conversationreadstatus rs
        SET last_read_message_id = (
            SELECT MAX(m.id)
            FROM conversations_message m
            WHERE m.conversation_id = rs.conversation_id
              AND m.created_at <= rs.last_read_at
        )
        WHERE rs.last_read_message_id IS NULL
        """
    )


class Migration(migrations.Migration):
    dependencies = [
        ('conversations', '0009_conversationreadstatus_last_read_message_id'),
    ]
    operations = [
        migrations.RunPython(backfill_high_water, migrations.RunPython.noop),
    ]
