"""M-Pesa rail tests.

The webhook views these used to cover are ``apps.payments`` endpoints now
(ADR-0033), and their quarantined legacy tests moved with them, to
``apps/payments/tests_mpesa_legacy.py``. What is left is the rail's own: the C2B
reconciler that stamps ``MpesaC2BTransaction``, and the stage gate over the
public auth endpoints.
"""
from decimal import Decimal
from unittest import skip
from unittest.mock import patch

# Quarantined under P0-02 — see GitHub issue #14. These cover the M-Pesa callback
# credit/reversal paths that Phase 0 rewrites onto post_journal()/reverse_journal()
# (P0-05); they will be rewritten and unskipped then.
_LEGACY = "P0-02 #14: legacy M-Pesa money-path test; rewrite onto post_journal() in P0-05"

from django.test import TestCase
from rest_framework.test import APIClient

from apps.communities.models import Community, CommunityMembership
from apps.contributions.models import Contribution, ContributionParticipant
from apps.users.models import User

from .models import MpesaC2BTransaction
from .services import MpesaService


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_user(phone="254700000001", name="Test User"):
    user = User.objects.create(phone_number=phone, name=name)
    user.set_pin("123456")
    user.is_pin_set = True
    user.is_phone_verified = True
    user.save()
    return user


def _make_community(creator):
    return Community.objects.create(
        name="Test Chama",
        created_by=creator,
        is_private=True,
    )


def _make_contribution(creator, community=None, is_active=True):
    return Contribution.objects.create(
        title="Monthly Savings",
        created_by=creator,
        community=community,
        target_amount=Decimal("10000.00"),
        amount_per_member=Decimal("500.00"),
        is_active=is_active,
    )


# ---------------------------------------------------------------------------
# reconcile_c2b — community membership gate
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class ReconcileC2BCommunityGateTest(TestCase):
    """
    The C2B auto-join bypass: a non-community-member pays into a private
    community contribution — they must NOT be added as a participant.
    """

    def setUp(self):
        self.admin    = _make_user("254700000010", "Admin")
        self.outsider = _make_user("254700000011", "Outsider")
        self.member   = _make_user("254700000012", "Member")

        self.community = _make_community(self.admin)
        # Admin is already a member (created as ADMIN by community creation).
        # Add `member` as an active member.
        CommunityMembership.objects.create(
            user=self.member,
            community=self.community,
            role=CommunityMembership.Role.MEMBER,
            is_active=True,
        )

        self.contrib = _make_contribution(self.admin, community=self.community)

    def _make_c2b_tx(self, user, receipt):
        return MpesaC2BTransaction.objects.create(
            phone_number=user.phone_number,
            amount=Decimal("500.00"),
            mpesa_receipt=receipt,
            transaction_date="2026-05-28T12:00:00Z",
            bill_ref_number=f"WEPL-{self.contrib.id}",
        )

    @patch("apps.contributions.services.ContributionService.contribute")
    def test_non_member_payment_not_auto_joined(self, mock_contribute):
        """Outsider pays into a community contribution — not added as participant."""
        tx = self._make_c2b_tx(self.outsider, "RCT_OUTSIDER")

        result = MpesaService.reconcile_c2b(tx)

        self.assertFalse(result)
        self.assertFalse(
            ContributionParticipant.objects.filter(
                contribution=self.contrib, user=self.outsider
            ).exists()
        )
        mock_contribute.assert_not_called()
        # Payment is recorded but flagged as un-reconciled for admin review.
        tx.refresh_from_db()
        self.assertFalse(tx.is_reconciled)

    @patch("apps.contributions.services.ContributionService.contribute")
    def test_community_member_payment_is_reconciled(self, mock_contribute):
        """Active community member pays — auto-joined as participant and reconciled."""
        tx = self._make_c2b_tx(self.member, "RCT_MEMBER")

        result = MpesaService.reconcile_c2b(tx)

        self.assertTrue(result)
        self.assertTrue(
            ContributionParticipant.objects.filter(
                contribution=self.contrib, user=self.member, is_active=True
            ).exists()
        )
        mock_contribute.assert_called_once()
        tx.refresh_from_db()
        self.assertTrue(tx.is_reconciled)

    @patch("apps.contributions.services.ContributionService.contribute")
    def test_open_contribution_no_community_auto_joins(self, mock_contribute):
        """Open contributions (no community) still auto-join any matching user."""
        open_contrib = _make_contribution(self.admin, community=None)
        tx = MpesaC2BTransaction.objects.create(
            phone_number=self.outsider.phone_number,
            amount=Decimal("500.00"),
            mpesa_receipt="RCT_OPEN",
            transaction_date="2026-05-28T12:00:00Z",
            bill_ref_number=f"WEPL-{open_contrib.id}",
        )

        result = MpesaService.reconcile_c2b(tx)

        self.assertTrue(result)
        self.assertTrue(
            ContributionParticipant.objects.filter(
                contribution=open_contrib, user=self.outsider
            ).exists()
        )


# ---------------------------------------------------------------------------
# Stage gate: auth endpoints are public, money endpoints are gated
# ---------------------------------------------------------------------------

class AuthEndpointPermissionTest(TestCase):
    """
    Verify that the DEFAULT_PERMISSION_CLASSES (IsActiveSession) does not
    block the three public auth endpoints, and does block data endpoints
    when called with no token.
    """

    def setUp(self):
        self.client = APIClient()

    def test_request_otp_requires_no_token(self):
        resp = self.client.post(
            "/api/auth/otp/request/",
            {"phone_number": "254700000099"},
            format="json",
        )
        # Should not be 401/403 — it's a public endpoint.
        # It may 400 (SMS backend not configured in test) or 200.
        self.assertNotIn(resp.status_code, [401, 403])

    def test_pin_login_requires_no_token(self):
        resp = self.client.post(
            "/api/auth/pin/login/",
            {"phone_number": "254700000099", "pin": "000000"},
            format="json",
        )
        self.assertNotIn(resp.status_code, [401, 403])

    def test_user_profile_requires_active_session(self):
        """Profile endpoint must reject unauthenticated requests."""
        resp = self.client.get("/api/users/profile/")
        self.assertEqual(resp.status_code, 401)

    @skip(_LEGACY)
    def test_stk_push_requires_active_session(self):
        """STK push is a money endpoint — must require active session."""
        resp = self.client.post(
            "/api/mpesa/stk-push/",
            {"payment_type": "contribution", "contribution_id": 1, "amount": 500},
            format="json",
        )
        self.assertEqual(resp.status_code, 401)
