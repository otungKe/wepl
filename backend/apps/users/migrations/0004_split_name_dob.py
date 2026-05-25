from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('users', '0003_kycprofile'),
    ]

    operations = [
        migrations.RenameField(
            model_name='kycprofile',
            old_name='full_name',
            new_name='given_names',
        ),
        migrations.AlterField(
            model_name='kycprofile',
            name='given_names',
            field=models.CharField(max_length=150),
        ),
        migrations.AddField(
            model_name='kycprofile',
            name='surname',
            field=models.CharField(default='', max_length=100),
            preserve_default=False,
        ),
    ]
