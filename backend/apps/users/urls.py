from django.urls import path
from .token_views import SessionTokenRefreshView
from .views import (
    RequestOTPView,
    VerifyOTPView,
    SetPINView,
    ResetPINView,
    PINLoginView,
    LogoutView,
    SessionListView,
    SessionRevokeView,
    SessionRevokeOthersView,
    ProtectedView,
    UserProfileView,
    KYCView,
    KYCEmailVerifyView,
    KYCResendEmailView,
    KYCResubmitView,
    KYCCheckIDView,
    KYCCheckEmailView,
    FinancialSummaryView,
    PrivacyPreferencesView,
    AccountDeletionView,
    VerificationRequestListView,
    VerificationRequestRespondView,
    PaymentMethodListCreateView,
    PaymentMethodDetailView,
    DataExportView,
)

urlpatterns = [
    # TOKEN REFRESH
    # The mobile client (api/client.ts) refreshes its 60-minute access token here
    # when it expires. SimpleJWT copies all non-reserved claims onto the new token,
    # so the custom `stage` and `sid` claims survive the refresh. ROTATE_REFRESH_TOKENS
    # + BLACKLIST_AFTER_ROTATION are on, and the session-aware view (ADR-0010) also
    # refuses to refresh a revoked session.
    path('token/refresh/', SessionTokenRefreshView.as_view()),

    # OTP FLOW
    path('otp/request/', RequestOTPView.as_view()),
    path('otp/verify/',  VerifyOTPView.as_view()),

    # PIN FLOW
    path('pin/set/',   SetPINView.as_view()),    # new users only
    path('pin/reset/', ResetPINView.as_view()),  # OTP-authenticated recovery
    path('pin/login/', PINLoginView.as_view()),  # normal login

    # SESSION MANAGEMENT (ADR-0010)
    path('logout/',                   LogoutView.as_view()),
    path('sessions/',                 SessionListView.as_view()),
    path('sessions/revoke-others/',   SessionRevokeOthersView.as_view()),
    path('sessions/<uuid:sid>/revoke/', SessionRevokeView.as_view()),

    # PROFILE
    path('profile/',           UserProfileView.as_view()),
    path('financial-summary/', FinancialSummaryView.as_view()),

    # KYC
    path('kyc/',                       KYCView.as_view()),
    path('kyc/resubmit/',              KYCResubmitView.as_view()),
    path('kyc/verify-email/',          KYCEmailVerifyView.as_view()),
    path('kyc/resend-verification/',   KYCResendEmailView.as_view()),
    path('kyc/check-id/',              KYCCheckIDView.as_view()),
    path('kyc/check-email/',           KYCCheckEmailView.as_view()),

    # VERIFICATION CENTER — ongoing compliance requests
    path('verification-requests/',                 VerificationRequestListView.as_view()),
    path('verification-requests/<int:pk>/respond/', VerificationRequestRespondView.as_view()),

    # PAYMENT METHODS — scalable payout rails (M-Pesa live; card/bank modelled)
    path('payment-methods/',                 PaymentMethodListCreateView.as_view()),
    path('payment-methods/<int:pk>/',        PaymentMethodDetailView.as_view()),
    path('payment-methods/<int:pk>/default/', PaymentMethodDetailView.as_view()),

    # DATA — self-serve export (data rights)
    path('data-export/', DataExportView.as_view()),

    # PRIVACY PREFERENCES
    path('privacy/', PrivacyPreferencesView.as_view()),

    # ACCOUNT DELETION (Kenya Data Protection Act 2019)
    path('account/', AccountDeletionView.as_view()),

    # TEST ROUTE
    path('protected/', ProtectedView.as_view()),
]