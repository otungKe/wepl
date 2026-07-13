"""Backfill the Program spine for existing funds (ADR-0026 Phase 0).

Every pre-spine Contribution / WelfareFund / SharesFund gets a Program row —
the exact rows ensure_program() creates at birth going forward: name from the
profile, organization from the community's spine row, tenant from the
community. Self-contained (historical models + the pure uuid7 helper).
"""
from django.db import migrations


def backfill(apps, schema_editor):
    from apps.core.ids import uuid7
    Program = apps.get_model('organizations', 'Program')

    specs = (
        ('Contribution', 'contribution', 'title'),
        ('WelfareFund',  'welfare',      'name'),
        ('SharesFund',   'shares',       'name'),
    )
    for model_name, program_type, name_field in specs:
        Fund = apps.get_model('contributions', model_name)
        for fund in Fund.objects.filter(program__isnull=True).select_related('community').iterator():
            community = getattr(fund, 'community', None)
            program = Program.objects.create(
                uid=uuid7(),
                name=getattr(fund, name_field, '') or '',
                program_type=program_type,
                organization_id=(community.organization_id if community else None),
                tenant_id=(community.tenant_id if community else None),
            )
            fund.program_id = program.id
            fund.save(update_fields=['program'])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [
        ('contributions', '0025_contribution_program_sharesfund_program_and_more'),
        ('organizations', '0002_program'),
        # Organizations must be backfilled first so programs can link to them.
        ('communities', '0021_backfill_organizations'),
    ]
    operations = [migrations.RunPython(backfill, noop)]
