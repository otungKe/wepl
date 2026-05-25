import uuid
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


def _generate_invite_code():
    return uuid.uuid4().hex[:10].upper()


def populate_invite_codes(apps, schema_editor):
    Community = apps.get_model('communities', 'Community')
    for community in Community.objects.all():
        community.invite_code = _generate_invite_code()
        community.save(update_fields=['invite_code'])


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0002_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        # Step 1: add nullable (no unique yet) so existing rows get a value
        migrations.AddField(
            model_name='community',
            name='invite_code',
            field=models.CharField(max_length=20, null=True, blank=True),
        ),
        # Step 2: populate unique codes for all existing rows
        migrations.RunPython(populate_invite_codes, migrations.RunPython.noop),
        # Step 3: make the field unique + non-nullable with callable default
        migrations.AlterField(
            model_name='community',
            name='invite_code',
            field=models.CharField(
                max_length=20,
                unique=True,
                default=_generate_invite_code,
                null=False,
                blank=False,
            ),
        ),
        migrations.CreateModel(
            name='CommunityJoinRequest',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('status', models.CharField(choices=[('PENDING', 'Pending'), ('APPROVED', 'Approved'), ('REJECTED', 'Rejected')], default='PENDING', max_length=10)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_at', models.DateTimeField(blank=True, null=True)),
                ('community', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_requests', to='communities.community')),
                ('requester', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='join_requests', to=settings.AUTH_USER_MODEL)),
                ('reviewed_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='reviewed_join_requests', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'unique_together': {('community', 'requester')},
            },
        ),
    ]
