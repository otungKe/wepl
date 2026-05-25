from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0008_restore_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='community',
            name='category',
            field=models.CharField(
                choices=[
                    ('savings',    'Savings'),
                    ('chama',      'Chama / Investment Club'),
                    ('investment', 'Investment'),
                    ('welfare',    'Welfare'),
                    ('emergency',  'Emergency Fund'),
                    ('business',   'Business'),
                    ('general',    'General'),
                ],
                default='general',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='community',
            name='location',
            field=models.CharField(blank=True, default='', max_length=120),
        ),
    ]
