from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('payments', '0002_initial'),
    ]

    operations = [
        # Payment history for a contribution, newest first
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['contribution', '-created_at'], name='payment_contrib_date_idx'),
        ),
        # Payments by user (personal payment history)
        migrations.AddIndex(
            model_name='payment',
            index=models.Index(fields=['user', '-created_at'], name='payment_user_date_idx'),
        ),
    ]
