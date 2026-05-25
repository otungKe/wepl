from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0003_community_invite_code_communityjoinrequest'),
    ]

    operations = [
        migrations.AddField(
            model_name='community',
            name='has_welfare_fund',
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name='community',
            name='has_shares_fund',
            field=models.BooleanField(default=False),
        ),
    ]
