"""Backfill member_status for pre-existing rows (Communities audit H-4).

Historical inactive memberships cannot distinguish "left" from "removed" —
both were is_active=False. LEFT is the safe default: it carries no penalty,
while REMOVED/BANNED start accruing only from actions taken after this ships.
"""
from django.db import migrations


def forwards(apps, schema_editor):
    CommunityMembership = apps.get_model('communities', 'CommunityMembership')
    CommunityMembership.objects.filter(is_active=False).update(member_status='left')
    CommunityMembership.objects.filter(is_active=True).update(member_status='active')


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0017_communitymembership_member_status'),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
