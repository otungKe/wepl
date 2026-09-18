"""Settlement-target registry semantics (ADR-0030 Slice B).

The per-context handlers themselves are covered by tests_settlement; these cover
the dispatcher: what happens for an unregistered context type, and the
asymmetric error handling between the settled and failed paths.
"""
from types import SimpleNamespace

from django.test import TestCase

from apps.contributions import settlement
from apps.contributions.settlement import (
    on_payout_failed, on_payout_settled, register_settlement_target,
    settlement_target_for,
)


def _ft(context_type, context_id=1):
    """The dispatchers only read these two attributes off the FT."""
    return SimpleNamespace(context_type=context_type, context_id=context_id)


class SettlementRegistryTests(TestCase):

    def test_contributions_targets_are_registered_at_startup(self):
        for ctx in ('welfare_claim', 'disbursement_request',
                    'emergency_advance', 'standing_order'):
            self.assertIsNotNone(settlement_target_for(ctx), ctx)

    def test_unknown_context_type_is_a_noop(self):
        on_payout_settled(_ft('not_a_real_context'), "R")
        on_payout_failed(_ft('not_a_real_context'))  # must not raise

    def test_missing_context_is_a_noop(self):
        on_payout_settled(_ft('', None), "R")
        on_payout_failed(_ft('welfare_claim', None))  # no id → no dispatch

    def test_target_without_a_failed_handler_is_a_noop(self):
        # standing_order registers on_settled only.
        on_payout_failed(_ft('standing_order', 42))  # must not raise

    def test_failed_path_swallows_a_raising_target(self):
        """A domain-update error must never break the money path."""
        name = 'test_ctx_raises'
        register_settlement_target(
            name, on_failed=lambda cid: (_ for _ in ()).throw(RuntimeError("boom")))
        self.addCleanup(lambda: settlement._TARGETS.pop(name, None))
        on_payout_failed(_ft(name, 7))  # swallowed + logged, not raised

    def test_settled_path_propagates_a_raising_target(self):
        """The settled path does not swallow: an unexpected error surfaces so the
        at-least-once delivery retries rather than silently losing the advance."""
        name = 'test_ctx_settled_raises'
        register_settlement_target(
            name, on_settled=lambda cid, receipt: (_ for _ in ()).throw(RuntimeError("boom")))
        self.addCleanup(lambda: settlement._TARGETS.pop(name, None))
        with self.assertRaises(RuntimeError):
            on_payout_settled(_ft(name, 7), "R")

    def test_handlers_receive_the_context_id_not_the_ft(self):
        """Targets must know nothing about the ledger — that is what lets the
        workflow dimension leave FT in a later slice."""
        seen = []
        name = 'test_ctx_args'
        register_settlement_target(name, on_settled=lambda cid, receipt: seen.append((cid, receipt)))
        self.addCleanup(lambda: settlement._TARGETS.pop(name, None))
        on_payout_settled(_ft(name, 99), "RCP")
        self.assertEqual(seen, [(99, "RCP")])
