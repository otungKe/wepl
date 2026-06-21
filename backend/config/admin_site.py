from django.contrib import admin
from django.urls import reverse


class WeplAdminSite(admin.AdminSite):
    """Platform admin with an at-a-glance overview on the index page."""

    site_header = 'WEPL Platform Admin'
    site_title  = 'WEPL Admin'
    index_title = 'Platform overview'

    def index(self, request, extra_context=None):
        extra_context = extra_context or {}
        extra_context['wepl_stats'] = self._overview()
        return super().index(request, extra_context)

    @staticmethod
    def _overview():
        from apps.communities.models import Community
        from apps.contributions.models import Contribution
        from apps.users.models import KYCProfile, User

        pending_url = reverse('admin:users_kycprofile_changelist') + '?status__exact=pending'
        return [
            {'label': 'KYC pending review', 'value': KYCProfile.objects.filter(status='pending').count(), 'url': pending_url},
            {'label': 'KYC approved',       'value': KYCProfile.objects.filter(status='approved').count()},
            {'label': 'KYC rejected',       'value': KYCProfile.objects.filter(status='rejected').count()},
            {'label': 'Total users',        'value': User.objects.count()},
            {'label': 'Active users',       'value': User.objects.filter(is_active=True).count()},
            {'label': 'Communities',        'value': Community.objects.count()},
            {'label': 'Contributions',      'value': Contribution.objects.count()},
        ]
