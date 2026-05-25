import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0004_welfare_shares'),
        ('contributions', '0004_overhaul'),
    ]

    operations = [
        # Remove has_welfare_fund / has_shares_fund from Contribution
        migrations.RemoveField(model_name='contribution', name='has_welfare_fund'),
        migrations.RemoveField(model_name='contribution', name='has_shares_fund'),

        # Remove contribution FK from WelfareFund (welfare is now community-only)
        migrations.RemoveField(model_name='welfarefund', name='contribution'),

        # Swap SharesFund.contribution → SharesFund.community
        migrations.RemoveField(model_name='sharesfund', name='contribution'),
        migrations.AddField(
            model_name='sharesfund',
            name='community',
            field=models.OneToOneField(
                null=True,
                blank=True,
                on_delete=django.db.models.deletion.CASCADE,
                related_name='shares_fund',
                to='communities.community',
            ),
        ),
    ]
