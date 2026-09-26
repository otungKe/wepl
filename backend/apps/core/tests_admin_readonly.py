"""Django admin is a viewer for money, controls and rail records.

Django admin sits outside the ops console's capabilities, step-up, maker-checker
and audit, so a superuser there must not be able to edit a payout's amount or
recipient, a claim, an advance, a hold or a payment intent. These tests hold
that for every admin registered on those models, so a new editable admin for one
of them fails the build.
"""
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase

from apps.contributions import models as contributions_models
from apps.controls.models import ControlDecision, HeldMovement
from apps.ledger.models import (
    Account, AccountBalance, FinancialTransaction, JournalEntry, JournalLine,
)
from apps.mpesa.models import MpesaC2BTransaction, MpesaSTKRequest
from apps.payments.models import PaymentIntent, ProviderEvent

#: Models whose admin must be view-only. ExchangeRate, LimitRule and
#: ReconciliationDrift stay editable on purpose (reference data, limit
#: configuration, and a drift's single sanctioned resolve() action).
READ_ONLY_MODELS = [
    FinancialTransaction, Account, AccountBalance, JournalEntry, JournalLine,
    HeldMovement, ControlDecision,
    MpesaSTKRequest, MpesaC2BTransaction,
    PaymentIntent, ProviderEvent,
    contributions_models.Contribution,
    contributions_models.ContributionParticipant,
    contributions_models.ROSCASlot,
    contributions_models.DisbursementRequest,
    contributions_models.DisbursementVote,
    contributions_models.WelfareFund,
    contributions_models.WelfareClaim,
    contributions_models.EmergencyAdvance,
]


class AdminReadOnlyTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.superuser = get_user_model().objects.create_superuser(
            phone_number="254700000999", password="x-not-used-x")

    def _request(self):
        request = RequestFactory().get("/admin/")
        request.user = self.superuser
        return request

    def test_superuser_cannot_add_change_or_delete(self):
        request = self._request()
        for model in READ_ONLY_MODELS:
            with self.subTest(model=model.__name__):
                model_admin = admin.site._registry.get(model)
                self.assertIsNotNone(model_admin, f"{model.__name__} is not registered")
                self.assertFalse(model_admin.has_add_permission(request))
                self.assertFalse(model_admin.has_change_permission(request))
                self.assertFalse(model_admin.has_delete_permission(request))
                # Still viewable: the admin remains a way to look things up.
                self.assertTrue(model_admin.has_view_permission(request))

    def test_no_admin_action_moves_money_or_releases_a_hold(self):
        request = self._request()
        claim_actions = admin.site._registry[contributions_models.WelfareClaim].get_actions(request)
        self.assertNotIn("force_disburse", claim_actions)
        hold_actions = admin.site._registry[HeldMovement].get_actions(request)
        self.assertNotIn("release_movements", hold_actions)
        self.assertNotIn("reject_movements", hold_actions)

    def test_c2b_retry_match_is_kept(self):
        # Re-running the automatic paybill match has no ops-console replacement
        # yet, and it cannot pick the member or the amount, so it stays.
        actions = admin.site._registry[MpesaC2BTransaction].get_actions(self._request())
        self.assertIn("force_reconcile", actions)
