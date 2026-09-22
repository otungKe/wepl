"""The Daraja URLs are a contract with Safaricom, not an internal detail.

``MPESA_CALLBACK_URL``, ``MPESA_B2C_RESULT_URL``, ``MPESA_B2C_TIMEOUT_URL`` and
the C2B URLs are configured on the Daraja portal. Moving the views out of
``apps/mpesa`` (ADR-0033) must not have moved a single path: a changed path is a
callback that 404s in production and a payment that is never credited.
"""
from django.test import TestCase
from django.urls import resolve

from apps.contributions.views import STKPushView
from apps.payments import views_mpesa

# path → the view that must answer it. Copied from the urlconf this replaced.
DARAJA_URLS = {
    "/api/mpesa/stk/push/":            STKPushView,
    "/api/mpesa/stk/callback/":        views_mpesa.STKCallbackView,
    "/api/mpesa/stk/status/ws_CO_1/":  views_mpesa.PendingSTKStatusView,
    "/api/mpesa/c2b/validate/":        views_mpesa.C2BValidationView,
    "/api/mpesa/c2b/confirm/":         views_mpesa.C2BCallbackView,
    "/api/mpesa/b2c/result/":          views_mpesa.B2CResultView,
    "/api/mpesa/b2c/timeout/":         views_mpesa.B2CTimeoutView,
}


class DarajaUrlContractTests(TestCase):

    def test_every_daraja_path_resolves_to_its_view(self):
        for path, view in DARAJA_URLS.items():
            with self.subTest(path=path):
                self.assertIs(resolve(path).func.view_class, view)

    def test_the_versioned_mount_carries_them_too(self):
        """config/api_urls.py is mounted at /api/ and /api/v1/ alike."""
        for path, view in DARAJA_URLS.items():
            versioned = path.replace("/api/", "/api/v1/", 1)
            with self.subTest(path=versioned):
                self.assertIs(resolve(versioned).func.view_class, view)
