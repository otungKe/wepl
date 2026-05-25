from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('communities', '0005_add_contribution_status'),
    ]

    operations = [
        # Most common: active members of a community
        migrations.AddIndex(
            model_name='communitymembership',
            index=models.Index(fields=['community', 'is_active'], name='membership_community_active_idx'),
        ),
        # User's active memberships (my communities list)
        migrations.AddIndex(
            model_name='communitymembership',
            index=models.Index(fields=['user', 'is_active'], name='membership_user_active_idx'),
        ),
        # Join requests filtered by community + status
        migrations.AddIndex(
            model_name='communityjoinrequest',
            index=models.Index(fields=['community', 'status'], name='join_req_community_status_idx'),
        ),
    ]
