"""The ledger's two inversion hooks (ADR-0033).

Both exist so the ledger can be handed something it must not import. What needs
proving is not the happy path — the rest of the suite exercises that through
``post_journal`` and account creation — but the edges that only appear because the
call is now indirect: what happens with nothing registered, and whether a check's
exception still reaches the caller.
"""
from decimal import Decimal

from django.test import SimpleTestCase

from apps.ledger import chokepoint, fund_tenant


class FundTenantResolverTests(SimpleTestCase):

    def setUp(self):
        self._saved = fund_tenant._resolver
        self.addCleanup(setattr, fund_tenant, "_resolver", self._saved)

    def test_unregistered_resolves_to_none(self):
        """No domain app installed → accounts are stamped shared, not an error."""
        fund_tenant._resolver = None
        self.assertIsNone(fund_tenant.resolve_fund_tenant("contribution", 1))

    def test_registered_resolver_is_used(self):
        fund_tenant.register_fund_tenant_resolver(
            lambda fund_type, fund_id: f"tenant:{fund_type}:{fund_id}")
        self.assertEqual(
            fund_tenant.resolve_fund_tenant("welfare", 7), "tenant:welfare:7")

    def test_a_failing_resolver_never_breaks_account_creation(self):
        """A pool whose community or tenant cannot be read must not stop a posting."""
        def boom(fund_type, fund_id):
            raise RuntimeError("community row is gone")

        fund_tenant.register_fund_tenant_resolver(boom)
        self.assertIsNone(fund_tenant.resolve_fund_tenant("shares", 3))

    def test_the_real_resolver_is_registered_at_startup(self):
        """ContributionsConfig.ready() must actually have wired itself in."""
        from apps.contributions.fund_tenant import tenant_for_fund
        self.assertIs(fund_tenant._resolver, tenant_for_fund)


class PrePostingChokepointTests(SimpleTestCase):

    def setUp(self):
        self._saved = list(chokepoint._checks)
        self.addCleanup(lambda: chokepoint._checks.__setitem__(slice(None), self._saved))

    def test_no_checks_registered_is_a_no_op(self):
        chokepoint._checks.clear()
        chokepoint.run_pre_posting_checks(financial_transaction=object(), amount=Decimal("1"))

    def test_every_registered_check_runs_with_the_movement(self):
        chokepoint._checks.clear()
        seen = []
        chokepoint.register_pre_posting_check(
            lambda *, financial_transaction, amount: seen.append(("a", amount)))
        chokepoint.register_pre_posting_check(
            lambda *, financial_transaction, amount: seen.append(("b", amount)))

        chokepoint.run_pre_posting_checks(
            financial_transaction=object(), amount=Decimal("250.00"))

        self.assertEqual(seen, [("a", Decimal("250.00")), ("b", Decimal("250.00"))])

    def test_a_check_that_raises_blocks_the_posting(self):
        """DENY/HOLD work by raising, so the exception must reach post_journal intact."""
        class Denied(Exception):
            pass

        chokepoint._checks.clear()
        def deny(*, financial_transaction, amount):
            raise Denied("over the daily limit")
        chokepoint.register_pre_posting_check(deny)

        with self.assertRaises(Denied) as ctx:
            chokepoint.run_pre_posting_checks(
                financial_transaction=object(), amount=Decimal("1"))
        self.assertEqual(str(ctx.exception), "over the daily limit")

    def test_registration_is_idempotent(self):
        """ready() can run more than once in a test process; controls must not double."""
        chokepoint._checks.clear()
        calls = []
        def check(*, financial_transaction, amount):
            calls.append(amount)

        chokepoint.register_pre_posting_check(check)
        chokepoint.register_pre_posting_check(check)
        chokepoint.run_pre_posting_checks(
            financial_transaction=object(), amount=Decimal("5"))

        self.assertEqual(calls, [Decimal("5")])

    def test_the_controls_gate_is_registered_at_startup(self):
        """ADR-0007's single enforcement point must be wired in, or nothing enforces."""
        from apps.controls.engine import enforce_controls
        self.assertIn(enforce_controls, chokepoint._checks)
