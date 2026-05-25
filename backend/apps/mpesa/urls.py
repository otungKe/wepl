from django.urls import path
from .views import (
    STKPushView,
    STKCallbackView,
    C2BValidationView,
    C2BCallbackView,
    PendingSTKStatusView,
    B2CResultView,
    B2CTimeoutView,
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
