from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('conversations', '0003_conversationreadstatus'),
    ]

    operations = [
        migrations.AddField(
            model_name='message',
            name='attachment',
            field=models.FileField(blank=True, null=True, upload_to='messages/'),
        ),
        migrations.AlterField(
            model_name='message',
            name='content',
            field=models.TextField(blank=True, default=''),
        ),
    ]
