from django.urls import path
from .views import (
    RequestOTPView,
    VerifyOTPView,
    SetPINView,
    ResetPINView,
    PINLoginView,
    ProtectedView,
    UserProfileView,
    KYCView,
    FinancialSummaryView,
)

urlpatterns = [
    # OTP FLOW
    path('otp/request/', RequestOTPView.as_view()),
    path('otp/verify/',  VerifyOTPView.as_view()),

    # PIN FLOW
    path('pin/set/',   SetPINView.as_view()),    # new users only
    path('pin/reset/', ResetPINView.as_view()),  # OTP-authenticated recovery
    path('pin/login/', PINLoginView.as_view()),  # normal login

    # PROFILE
    path('profile/',           UserProfileView.as_view()),
    path('financial-summary/', FinancialSummaryView.as_view()),

    # KYC
    path('kyc/', KYCView.as_view()),

    # TEST ROUTE
    path('protected/', ProtectedView.as_view()),
]