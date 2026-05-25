from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Reminder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('reminder_type', models.CharField(choices=[('contribution_due', 'Contribution Due'), ('welfare_contrib', 'Welfare Contribution'), ('advance_repayment', 'Advance Repayment'), ('standing_order', 'Standing Order'), ('custom', 'Custom')], default='custom', max_length=25)),
                ('title', models.CharField(max_length=150)),
                ('note', models.TextField(blank=True, default='')),
                ('contribution_id', models.PositiveIntegerField(blank=True, null=True)),
                ('community_id', models.PositiveIntegerField(blank=True, null=True)),
                ('scheduled_for', models.DateTimeField()),
                ('recurrence', models.CharField(choices=[('none', 'One-time'), ('daily', 'Daily'), ('weekly', 'Weekly'), ('monthly', 'Monthly')], default='none', max_length=10)),
                ('next_fire_at', models.DateTimeField()),
                ('is_active', models.BooleanField(db_index=True, default=True)),
                ('last_sent_at', models.DateTimeField(blank=True, null=True)),
                ('send_count', models.PositiveIntegerField(default=0)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('user', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reminders', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'ordering': ['next_fire_at'],
            },
        ),
        migrations.AddIndex(
            model_name='reminder',
            index=models.Index(fields=['user', 'is_active', 'next_fire_at'], name='reminder_user_active_fire_idx'),
        ),
    ]
