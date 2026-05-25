from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0015_contribution_created_by_protect'),
    ]

    operations = [
        migrations.AddField(
            model_name='contribution',
            name='is_campaign',
            field=models.BooleanField(
                default=False,
                help_text='Marks this as a public fundraising campaign (visible in Discover).',
            ),
        ),
    ]
