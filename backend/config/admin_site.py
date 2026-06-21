from unfold.sites import UnfoldAdminSite


class WeplAdminSite(UnfoldAdminSite):
    """WEPL platform admin, themed with django-unfold.

    Branding, colours and the sidebar live in the ``UNFOLD`` setting
    (config.settings.base); this subclass only exists so a custom admin site
    is wired via WeplAdminConfig.default_site.
    """


def kyc_pending_badge(request):
    """Live count of KYC submissions awaiting review, shown on the sidebar."""
    from apps.users.models import KYCProfile

    return KYCProfile.objects.filter(status="pending").count() or None
