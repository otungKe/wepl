from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('activity', '0002_initial'),
    ]

    operations = [
        # Activity feed: user's activity ordered newest-first
        migrations.AddIndex(
            model_name='activity',
            index=models.Index(fields=['user', '-created_at'], name='activity_user_date_idx'),
        ),
    ]
