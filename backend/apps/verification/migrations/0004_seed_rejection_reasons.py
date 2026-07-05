"""Seed the coded rejection catalogue (V4). Codes are stable identifiers —
analytics and events aggregate on them — so edit labels/messages in place
rather than renaming codes."""
from django.db import migrations

REASONS = [
    ('DOC_UNREADABLE', 'Document photo unclear / unreadable',
     'The photos of your ID were not clear enough to verify. Please re-take '
     'them in good lighting, with all four corners visible and no glare.', 10),
    ('DOC_INVALID', 'Not a valid Kenyan National ID',
     'The document you provided could not be accepted. Please submit clear '
     'photos of your valid Kenyan National ID (front and back).', 20),
    ('DETAILS_MISMATCH', 'Typed details do not match the document',
     'The details you entered do not match your ID document. Please check '
     'your ID number, names, and date of birth, then re-submit.', 30),
    ('SELFIE_MISMATCH', 'Selfie does not match the ID photo',
     'We could not match your selfie to the photo on your ID. Please re-take '
     'your selfie in good lighting, facing the camera directly.', 40),
    ('ID_IN_USE', 'ID number registered to another account',
     'This ID number is already registered to another account. If you believe '
     'this is an error, please contact support.', 50),
    ('UNDERAGE', 'Applicant under 18',
     'You must be at least 18 years old to complete identity verification.', 60),
    ('SUSPECTED_FRAUD', 'Suspected fraudulent submission',
     'We could not verify your identity from the information provided.', 70),
    ('OTHER', 'Other (free-text reason shown to the applicant)',
     '', 999),
]


def forwards(apps, schema_editor):
    RejectionReason = apps.get_model('verification', 'RejectionReason')
    for code, label, message, sort in REASONS:
        RejectionReason.objects.update_or_create(
            code=code,
            defaults={'label': label, 'customer_message': message,
                      'active': True, 'sort': sort},
        )


def backwards(apps, schema_editor):
    RejectionReason = apps.get_model('verification', 'RejectionReason')
    RejectionReason.objects.filter(code__in=[r[0] for r in REASONS]).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('verification', '0003_rejectionreason_verificationcase_assigned_to_and_more'),
    ]

    operations = [
        migrations.RunPython(forwards, backwards),
    ]
