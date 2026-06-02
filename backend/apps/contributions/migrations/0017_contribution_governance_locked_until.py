from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0016_add_is_campaign'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribution',
            name='governance_locked_until',
            field=models.DateTimeField(
                blank=True,
                null=True,
                help_text=(
                    'Disbursements cannot execute until this timestamp passes '
                    'after a governance change.'
                ),
            ),
        ),
    ]
