from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0006_messagereaction'),
    ]

    operations = [
        # Chat history: messages ordered newest-first per conversation
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['conversation', '-created_at'], name='msg_conv_date_idx'),
        ),
        # Filter out soft-deleted messages
        migrations.AddIndex(
            model_name='message',
            index=models.Index(fields=['conversation', 'is_deleted'], name='msg_conv_deleted_idx'),
        ),
        # Unread messages: newer than last_read_at per conversation+user
        migrations.AddIndex(
            model_name='conversationreadstatus',
            index=models.Index(fields=['conversation', 'user'], name='conv_read_conv_user_idx'),
        ),
    ]
