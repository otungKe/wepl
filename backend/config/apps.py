from django.contrib.admin.apps import AdminConfig


class WeplAdminConfig(AdminConfig):
    """Use the WEPL admin site (with the overview dashboard) as the default."""
    default_site = 'config.admin_site.WeplAdminSite'
