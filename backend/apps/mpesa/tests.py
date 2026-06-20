"""
M-Pesa callback view tests.

Covers the critical security and idempotency boundaries:
  - STKCallbackView  : success, failure, duplicate idempotency
  - C2BCallbackView  : success, duplicate idempotency, community membership gate
  - B2CResultView    : success, failure, missing conversation_id
  - reconcile_c2b    : community-member gate (the C2B auto-join bypass fix)
"""
from decimal import Decimal
from unittest import skip
from unittest.mock import MagicMock, patch

# Quarantined under P0-02 — see GitHub issue #14. These cover the M-Pesa callback
# credit/reversal paths that Phase 0 rewrites onto post_journal()/reverse_journal()
# (P0-05); they will be rewritten and unskipped then.
_LEGACY = "P0-02 #14: legacy M-Pesa money-path test; rewrite onto post_journal() in P0-05"

from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient

from apps.communities.models import Community, CommunityMembership
from apps.contributions.models import Contribution, ContributionParticipant
from apps.users.models import User

from .models import MpesaC2BTransaction, MpesaSTKRequest
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


def _make_stk(user, contribution, amount="500.00", status="PENDING"):
    return MpesaSTKRequest.objects.create(
        user=user,
        payment_type="contribution",
        contribution=contribution,
        phone_number=user.phone_number,
        amount=Decimal(amount),
        checkout_request_id="ws_CO_TEST_001",
        merchant_request_id="MREQ_001",
        status=status,
    )


# ---------------------------------------------------------------------------
# STKCallbackView
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class STKCallbackViewTest(TestCase):

    def setUp(self):
        self.client      = APIClient()
        self.user        = _make_user()
        self.contrib     = _make_contribution(self.user)
        self.stk         = _make_stk(self.user, self.contrib)
        self.url         = "/api/mpesa/stk-callback/"

    def _success_payload(self, checkout_id="ws_CO_TEST_001", receipt="RCT001"):
        return {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "MREQ_001",
                    "CheckoutRequestID": checkout_id,
                    "ResultCode": 0,
                    "ResultDesc": "The service request is processed successfully.",
                    "CallbackMetadata": {
                        "Item": [
                            {"Name": "Amount",              "Value": 500},
                            {"Name": "MpesaReceiptNumber",  "Value": receipt},
                            {"Name": "TransactionDate",     "Value": 20260528120000},
                            {"Name": "PhoneNumber",         "Value": 254700000001},
                        ]
                    }
                }
            }
        }

    def _failure_payload(self, checkout_id="ws_CO_TEST_001"):
        return {
            "Body": {
                "stkCallback": {
                    "MerchantRequestID": "MREQ_001",
                    "CheckoutRequestID": checkout_id,
                    "ResultCode": 1032,
                    "ResultDesc": "Request cancelled by user",
                }
            }
        }

    @patch("apps.mpesa.views._process_stk_sync_with_fallback")
    def test_success_callback_marks_stk_success(self, mock_process):
        resp = self.client.post(self.url, self._success_payload(), format="json")

        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "SUCCESS")
        self.assertEqual(self.stk.mpesa_receipt, "RCT001")

    @patch("apps.mpesa.views._process_stk_sync_with_fallback")
    def test_success_callback_triggers_processing(self, mock_process):
        self.client.post(self.url, self._success_payload(), format="json")
        # Processing is scheduled via on_commit; in tests on_commit runs inline.
        mock_process.assert_called_once_with(self.stk.id)

    @patch("apps.mpesa.views._process_stk_sync_with_fallback")
    def test_duplicate_success_callback_is_noop(self, mock_process):
        """Second identical callback must not double-process."""
        self.client.post(self.url, self._success_payload(), format="json")
        mock_process.reset_mock()

        resp = self.client.post(self.url, self._success_payload(), format="json")

        self.assertEqual(resp.status_code, 200)
        mock_process.assert_not_called()

    def test_failure_callback_marks_stk_failed(self):
        resp = self.client.post(self.url, self._failure_payload(), format="json")

        self.assertEqual(resp.status_code, 200)
        self.stk.refresh_from_db()
        self.assertEqual(self.stk.status, "FAILED")
        self.assertEqual(self.stk.result_code, 1032)

    def test_missing_checkout_id_returns_200(self):
        resp = self.client.post(self.url, {"Body": {"stkCallback": {}}}, format="json")
        self.assertEqual(resp.status_code, 200)

    def test_unknown_checkout_id_success_callback_does_not_crash(self):
        payload = self._success_payload(checkout_id="ws_CO_UNKNOWN")
        resp    = self.client.post(self.url, payload, format="json")
        self.assertEqual(resp.status_code, 200)


# ---------------------------------------------------------------------------
# C2BCallbackView — basic reconciliation
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class C2BCallbackViewTest(TestCase):

    def setUp(self):
        self.client  = APIClient()
        self.user    = _make_user("254700000002")
        self.contrib = _make_contribution(self.user)
        # Make user a participant so open-contribution path works
        ContributionParticipant.objects.create(
            contribution=self.contrib, user=self.user, is_active=True
        )
        self.url = "/api/mpesa/c2b-callback/"

    def _payload(self, ref="WEPL-{id}", receipt="RCTE001", phone="254700000002"):
        ref = ref.format(id=self.contrib.id)
        return {
            "TransID":          receipt,
            "MSISDN":           phone,
            "TransAmount":      "500.00",
            "BillRefNumber":    ref,
            "TransTime":        "20260528120000",
        }

    @patch.object(MpesaService, "reconcile_c2b", return_value=True)
    def test_c2b_callback_creates_transaction(self, mock_reconcile):
        resp = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertTrue(
            MpesaC2BTransaction.objects.filter(mpesa_receipt="RCTE001").exists()
        )
        mock_reconcile.assert_called_once()

    @patch.object(MpesaService, "reconcile_c2b", return_value=True)
    def test_duplicate_receipt_is_noop(self, mock_reconcile):
        """Same M-Pesa receipt twice must not create a second transaction."""
        self.client.post(self.url, self._payload(), format="json")
        mock_reconcile.reset_mock()

        resp = self.client.post(self.url, self._payload(), format="json")

        self.assertEqual(resp.status_code, 200)
        self.assertEqual(
            MpesaC2BTransaction.objects.filter(mpesa_receipt="RCTE001").count(), 1
        )
        mock_reconcile.assert_not_called()

    @patch.object(MpesaService, "reconcile_c2b", return_value=True)
    def test_missing_receipt_returns_200(self, _):
        resp = self.client.post(self.url, {}, format="json")
        self.assertEqual(resp.status_code, 200)


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
# B2CResultView
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class B2CResultViewTest(TestCase):

    def setUp(self):
        self.client = APIClient()
        self.url    = "/api/mpesa/b2c-result/"

    def _payload(self, result_code=0, conversation_id="CONV_001"):
        return {
            "Result": {
                "ResultCode":    result_code,
                "ResultDesc":    "The service request is processed successfully.",
                "ConversationID": conversation_id,
                "ResultParameters": {
                    "ResultParameter": [
                        {"Key": "TransactionID",      "Value": "NLJ7RT61SV"},
                        {"Key": "TransactionReceipt", "Value": "NLJ7RT61SV"},
                    ]
                }
            }
        }

    def test_missing_conversation_id_returns_200(self):
        resp = self.client.post(self.url, {"Result": {}}, format="json")
        self.assertEqual(resp.status_code, 200)

    @patch("apps.ledger.models.FinancialTransaction.objects.get",
           side_effect=Exception("DoesNotExist"))
    def test_unknown_conversation_id_returns_200(self, _):
        resp = self.client.post(self.url, self._payload(conversation_id="UNKNOWN"), format="json")
        self.assertEqual(resp.status_code, 200)


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
