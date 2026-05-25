from django.urls import path

from .views import ContributionPaymentsView

urlpatterns = [
    # GET /api/payments/contribution/<id>/
    # Read-only list of legacy Payment records for a contribution.
    path(
        'contribution/<int:contribution_id>/',
        ContributionPaymentsView.as_view(),
    ),
]
