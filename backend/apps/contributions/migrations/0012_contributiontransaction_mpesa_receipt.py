from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('contributions', '0011_performance_indexes'),
    ]

    operations = [
        migrations.AddField(
            model_name='contributiontransaction',
            name='mpesa_receipt',
            field=models.CharField(blank=True, max_length=50, null=True),
        ),
    ]
