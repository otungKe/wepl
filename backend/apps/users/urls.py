from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView
from .views import (
    RequestOTPView,
    VerifyOTPView,
    SetPINView,
    ResetPINView,
    PINLoginView,
    ProtectedView,
    UserProfileView,
    KYCView,
    KYCEmailVerifyView,
    KYCResendEmailView,
    KYCCheckIDView,
    KYCCheckEmailView,
    FinancialSummaryView,
    PrivacyPreferencesView,
    AccountDeletionView,
)

urlpatterns = [
    # TOKEN REFRESH
    # The mobile client (api/client.ts) refreshes its 60-minute access token here
    # when it expires. SimpleJWT's TokenRefreshView copies all non-reserved claims
    # onto the new access token, so the custom `stage` claim minted by issue_tokens
    # survives the refresh. ROTATE_REFRESH_TOKENS + BLACKLIST_AFTER_ROTATION are on,
    # so a rotated refresh token is returned and the old one is blacklisted.
    path('token/refresh/', TokenRefreshView.as_view()),

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
    path('kyc/',                       KYCView.as_view()),
    path('kyc/verify-email/',          KYCEmailVerifyView.as_view()),
    path('kyc/resend-verification/',   KYCResendEmailView.as_view()),
    path('kyc/check-id/',              KYCCheckIDView.as_view()),
    path('kyc/check-email/',           KYCCheckEmailView.as_view()),

    # PRIVACY PREFERENCES
    path('privacy/', PrivacyPreferencesView.as_view()),

    # ACCOUNT DELETION (Kenya Data Protection Act 2019)
    path('account/', AccountDeletionView.as_view()),

    # TEST ROUTE
    path('protected/', ProtectedView.as_view()),
]