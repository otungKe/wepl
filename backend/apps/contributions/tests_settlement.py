"""Contract tests for the settlement seam (apps.contributions.settlement) — the
provider-agnostic domain reaction to a settled payout, relocated out of the mpesa
rail app and the ledger (Move 1). The per-context routing is exercised end-to-end
by the mpesa B2C callback and ops-recovery suites; these lock the public entry
points and the context-free no-op paths."""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.ledger.models import FinancialTransaction as FT
from apps.contributions import settlement


class SettlementSeamTests(TestCase):
    def _ft(self, **kw):
        return FT.objects.create(
            op_type=FT.OpType.DISBURSEMENT, state=FT.State.PROCESSING,
            amount=Decimal("100.00"),
            initiated_by=get_user_model().objects.create(phone_number="254700000601"),
            idempotency_key=kw.pop("idempotency_key", "settle-1"), **kw)

    def test_no_context_is_a_noop(self):
        # An FT with no linked domain object (e.g. a manual adjustment) must not
        # raise on either path.
        ft = self._ft(context_type="", context_id=None)
        settlement.on_payout_settled(ft, "RCPT")   # no raise
        settlement.on_payout_failed(ft)            # no raise

    def test_standing_order_success_is_logging_only(self):
        ft = self._ft(context_type="standing_order", context_id=42,
                      idempotency_key="settle-so")
        settlement.on_payout_settled(ft, "RCPT")   # logs, no domain object, no raise

    def test_missing_domain_object_is_swallowed(self):
        # A context pointing at a non-existent row is tolerated (idempotent /
        # already-cleaned-up), never raised.
        ft = self._ft(context_type="welfare_claim", context_id=999999,
                      idempotency_key="settle-missing")
        settlement.on_payout_settled(ft, "RCPT")
        settlement.on_payout_failed(ft)
