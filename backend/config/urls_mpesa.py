"""The Daraja URL map.

**These paths are registered with Safaricom** (``MPESA_CALLBACK_URL``,
``MPESA_B2C_RESULT_URL``, ``MPESA_B2C_TIMEOUT_URL``, and the C2B URLs set on the
Daraja portal). Changing one silently breaks a live callback, so the map is kept
byte-identical to the ``apps/mpesa/urls.py`` it replaced.

It lives in ``config`` rather than in an app because the views no longer belong
to one app: the pay-in endpoint is a contributions endpoint and the webhooks are
payments endpoints, while ``apps.mpesa`` is now only the Daraja wire client
(ADR-0005, ADR-0033). A project-level map is the one place that may name both.
"""
from django.urls import path

from apps.contributions.views import STKPushView
from apps.payments.views_mpesa import (
    B2CResultView,
    B2CTimeoutView,
    C2BCallbackView,
    C2BValidationView,
    PendingSTKStatusView,
    STKCallbackView,
)

urlpatterns = [
    path('stk/push/',                              STKPushView.as_view()),
    path('stk/callback/',                          STKCallbackView.as_view()),
    path('stk/status/<str:checkout_request_id>/',  PendingSTKStatusView.as_view()),
    path('c2b/validate/',                          C2BValidationView.as_view()),
    path('c2b/confirm/',                           C2BCallbackView.as_view()),
    path('b2c/result/',                            B2CResultView.as_view()),
    path('b2c/timeout/',                           B2CTimeoutView.as_view()),
]
