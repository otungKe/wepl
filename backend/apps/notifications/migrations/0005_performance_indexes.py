from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('notifications', '0004_notification_join_request_id_and_more'),
    ]

    operations = [
        # Most common query: user's unread notifications
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read', '-created_at'], name='notif_user_read_date_idx'),
        ),
        # Unread count query: filter(user=u, is_read=False)
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read'], name='notif_user_read_idx'),
        ),
    ]
