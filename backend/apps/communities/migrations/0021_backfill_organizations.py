"""Backfill the Organization spine for existing communities (ADR-0026 Phase 0).

Every pre-spine community gets an Organization row (archetype 'community',
same tenant) — the exact rows ensure_organization_for_community() creates at
birth going forward. Self-contained: uses historical models + the uuid7 helper
(pure function, safe to import in a migration, same as ledger 0011/0014).
"""
from django.db import migrations


def backfill(apps, schema_editor):
    from apps.core.ids import uuid7
    Community = apps.get_model('communities', 'Community')
    Organization = apps.get_model('organizations', 'Organization')

    for community in Community.objects.filter(organization__isnull=True).iterator():
        org = Organization.objects.create(
            uid=uuid7(),
            name=community.name,
            archetype='community',
            tenant_id=community.tenant_id,
        )
        community.organization_id = org.id
        community.save(update_fields=['organization'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('communities', '0020_community_organization'),
        ('organizations', '0001_initial'),
    ]
    operations = [migrations.RunPython(backfill, noop)]
