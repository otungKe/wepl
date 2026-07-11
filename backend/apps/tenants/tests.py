"""Multi-tenancy foundation tests — tenant model, resolution, and
tenant-scoped reporting isolation."""
from decimal import Decimal

from django.test import TestCase

from apps.ledger import reporting
from apps.ledger.models import Account, JournalLine
from apps.ledger.posting import Line, post_journal
from apps.tenants.models import Tenant
from apps.tenants.resolve import default_tenant, tenant_for_community, tenant_for_user


class TenantResolutionTests(TestCase):
    def test_default_tenant_is_idempotent(self):
        a = default_tenant()
        b = default_tenant()
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.slug, 'default')

    def test_tenant_for_community_falls_back_to_default(self):
        class _C:  # community without a tenant set
            tenant = None
        self.assertEqual(tenant_for_community(_C()).pk, default_tenant().pk)


class TenantScopedReportingTests(TestCase):
    """Reports filtered by tenant never read another tenant's financial data."""

    def setUp(self):
        self.t1 = Tenant.objects.create(name='SACCO One', slug='sacco-one')
        self.t2 = Tenant.objects.create(name='SACCO Two', slug='sacco-two')

        # Each tenant gets its own pair of accounts and a posted journal.
        self.a1 = Account.objects.create(code='T1-A', name='t1 asset', type=Account.Type.ASSET, tenant=self.t1)
        self.l1 = Account.objects.create(code='T1-L', name='t1 liab', type=Account.Type.LIABILITY, tenant=self.t1)
        self.a2 = Account.objects.create(code='T2-A', name='t2 asset', type=Account.Type.ASSET, tenant=self.t2)
        self.l2 = Account.objects.create(code='T2-L', name='t2 liab', type=Account.Type.LIABILITY, tenant=self.t2)

        post_journal(idempotency_key='t1-j', op_type='CONTRIBUTION', lines=[
            Line(account=self.a1, direction=JournalLine.Direction.DEBIT, amount=Decimal('1000')),
            Line(account=self.l1, direction=JournalLine.Direction.CREDIT, amount=Decimal('1000')),
        ])
        post_journal(idempotency_key='t2-j', op_type='CONTRIBUTION', lines=[
            Line(account=self.a2, direction=JournalLine.Direction.DEBIT, amount=Decimal('250')),
            Line(account=self.l2, direction=JournalLine.Direction.CREDIT, amount=Decimal('250')),
        ])

    def test_trial_balance_is_isolated_per_tenant(self):
        tb1 = reporting.trial_balance(tenant_id=self.t1.id)
        self.assertEqual(tb1['total_debit'], Decimal('1000'))
        self.assertTrue(tb1['balanced'])
        self.assertEqual({r['code'] for r in tb1['rows']}, {'T1-A', 'T1-L'})

        tb2 = reporting.trial_balance(tenant_id=self.t2.id)
        self.assertEqual(tb2['total_debit'], Decimal('250'))
        self.assertEqual({r['code'] for r in tb2['rows']}, {'T2-A', 'T2-L'})

    def test_global_trial_balance_sees_both(self):
        tb = reporting.trial_balance()
        self.assertEqual(tb['total_debit'], Decimal('1250'))
        self.assertTrue(tb['balanced'])

    def test_balance_sheet_per_tenant(self):
        bs = reporting.balance_sheet(tenant_id=self.t1.id)
        self.assertEqual(bs['assets'], Decimal('1000'))
        self.assertEqual(bs['liabilities'], Decimal('1000'))
        self.assertTrue(bs['balanced'])


class CommunityGetsTenantOnCreateTests(TestCase):
    def test_new_community_is_assigned_a_tenant(self):
        from django.contrib.auth import get_user_model
        from apps.communities.services import CommunityService
        user = get_user_model().objects.create_user(phone_number='254700000020')
        community = CommunityService.create_community(user, {'name': 'Test Chama'})
        self.assertIsNotNone(community.tenant_id)
        self.assertEqual(community.tenant.slug, 'default')


class TenantContextWiringTests(TestCase):
    """JWT auth pins the RLS context for members; middleware resets it."""

    def _guc(self):
        from django.db import connection
        with connection.cursor() as c:
            c.execute("SELECT current_setting('app.tenant_id', true)")
            return c.fetchone()[0]

    def _request_with_token(self, user):
        from rest_framework.test import APIRequestFactory
        from rest_framework_simplejwt.tokens import AccessToken
        token = str(AccessToken.for_user(user))
        return APIRequestFactory().get('/', HTTP_AUTHORIZATION=f'Bearer {token}')

    def test_member_request_pins_tenant(self):
        from django.contrib.auth import get_user_model
        from apps.tenants.auth import TenantJWTAuthentication
        from apps.tenants.rls import clear_current_tenant
        from apps.tenants.resolve import default_tenant
        clear_current_tenant()
        user = get_user_model().objects.create_user(phone_number='254700000030')
        TenantJWTAuthentication().authenticate(self._request_with_token(user))
        self.assertEqual(self._guc(), str(default_tenant().id))

    def test_staff_request_not_pinned(self):
        from django.contrib.auth import get_user_model
        from apps.tenants.auth import TenantJWTAuthentication
        from apps.tenants.rls import clear_current_tenant
        clear_current_tenant()
        staff = get_user_model().objects.create_user(phone_number='254700000031')
        staff.is_staff = True
        staff.save()
        TenantJWTAuthentication().authenticate(self._request_with_token(staff))
        self.assertEqual(self._guc(), '')  # left unset → cross-tenant operator

    def test_middleware_resets_context(self):
        from django.http import HttpResponse
        from apps.tenants.middleware import TenantRLSMiddleware
        from apps.tenants.rls import set_current_tenant
        from apps.tenants.resolve import default_tenant
        set_current_tenant(default_tenant().id)
        mw = TenantRLSMiddleware(lambda req: HttpResponse('ok'))
        mw(self._request_with_token(None) if False else object())  # request unused by middleware
        self.assertEqual(self._guc(), '')


class PerTenantChartOfAccountsTests(TestCase):
    """member sub-ledgers and financial transactions inherit the fund's tenant."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        from apps.communities.models import Community
        from apps.contributions.models import WelfareFund
        self.t1 = Tenant.objects.create(name='Coa Tenant', slug='coa-tenant')
        self.user = get_user_model().objects.create_user(phone_number='254700000040')
        self.community = Community.objects.create(created_by=self.user, name='Coa C', tenant=self.t1)
        self.fund = WelfareFund.objects.create(community=self.community, monthly_contribution=Decimal('0'))

    def test_member_subledger_inherits_tenant(self):
        from apps.ledger.coa import member_fund_account
        acct = member_fund_account(user=self.user, fund_type='welfare', fund_id=self.fund.id)
        self.assertEqual(acct.tenant_id, self.t1.id)

    def test_financial_transaction_inherits_tenant(self):
        from apps.ledger.writer import create_fin_transaction
        ft, _ = create_fin_transaction(
            idempotency_key='coa-ft-1', op_type='WELFARE_CONTRIBUTION',
            amount=Decimal('100'), initiated_by=self.user, welfare_fund=self.fund,
        )
        self.assertEqual(ft.tenant_id, self.t1.id)


class PerTenantLimitsTests(TestCase):
    """limit rules can be scoped to a tenant; global rules apply to all."""

    def setUp(self):
        from django.contrib.auth import get_user_model
        self.t1 = Tenant.objects.create(name='Lim One', slug='lim-one')
        self.t2 = Tenant.objects.create(name='Lim Two', slug='lim-two')
        self.user = get_user_model().objects.create_user(phone_number='254700000041')

    def test_tenant_rule_applies_only_to_its_tenant(self):
        from apps.controls.engine import evaluate
        from apps.controls.models import ControlDecision, LimitRule
        LimitRule.objects.create(name='t1 cap', tenant=self.t1, direction='PAYOUT',
                                 period='TXN', max_amount=Decimal('100'), action='DENY')
        d1 = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT', direction='PAYOUT',
                      amount=Decimal('500'), tenant_id=self.t1.id)
        self.assertEqual(d1.decision, ControlDecision.Outcome.DENY)
        d2 = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT', direction='PAYOUT',
                      amount=Decimal('500'), tenant_id=self.t2.id)
        self.assertEqual(d2.decision, ControlDecision.Outcome.ALLOW)

    def test_global_rule_applies_to_all_tenants(self):
        from apps.controls.engine import evaluate
        from apps.controls.models import ControlDecision, LimitRule
        LimitRule.objects.create(name='global cap', direction='PAYOUT', period='TXN',
                                 max_amount=Decimal('100'), action='DENY')
        d = evaluate(subject_user_id=self.user.id, op_type='DISBURSEMENT', direction='PAYOUT',
                     amount=Decimal('500'), tenant_id=self.t2.id)
        self.assertEqual(d.decision, ControlDecision.Outcome.DENY)


class RowLevelSecurityTests(TestCase):
    """prove RLS isolates tenants at the database, not just the ORM.

    The CI/dev DB role is a superuser (which bypasses RLS), so we SET ROLE to a
    freshly-created NON-superuser role — the production scenario — and verify that
    even raw SQL cannot read another tenant's rows once app.tenant_id is set.
    """

    def setUp(self):
        from django.db import connection
        self.t1 = Tenant.objects.create(name='RLS One', slug='rls-one')
        self.t2 = Tenant.objects.create(name='RLS Two', slug='rls-two')
        Account.objects.create(code='R1-A', name='r1', type=Account.Type.ASSET, tenant=self.t1)
        Account.objects.create(code='R2-A', name='r2', type=Account.Type.ASSET, tenant=self.t2)
        with connection.cursor() as cur:
            cur.execute("DROP ROLE IF EXISTS rls_probe")
            cur.execute("CREATE ROLE rls_probe NOSUPERUSER")
            cur.execute("GRANT SELECT ON ledger_account TO rls_probe")

    def _codes_as_tenant(self, tenant_id):
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute("SET ROLE rls_probe")
            try:
                cur.execute("SELECT set_config('app.tenant_id', %s, false)", [str(tenant_id)])
                cur.execute("SELECT code FROM ledger_account WHERE code LIKE 'R%%' ORDER BY code")
                return [r[0] for r in cur.fetchall()]
            finally:
                cur.execute("RESET ROLE")
                cur.execute("RESET app.tenant_id")

    def test_rls_blocks_cross_tenant_reads(self):
        self.assertEqual(self._codes_as_tenant(self.t1.id), ['R1-A'])
        self.assertEqual(self._codes_as_tenant(self.t2.id), ['R2-A'])

    def test_superuser_unset_context_sees_all(self):
        # No app.tenant_id set + superuser session (the default ORM connection)
        # → system access sees both tenants' rows.
        codes = set(Account.objects.filter(code__startswith='R').values_list('code', flat=True))
        self.assertEqual(codes, {'R1-A', 'R2-A'})


class CrossTenantGuardTests(TestCase):
    """guard_tenant blocks + audits cross-tenant access; allows same/unset."""

    def setUp(self):
        self.t1 = Tenant.objects.create(name='Guard One', slug='guard-one')
        self.t2 = Tenant.objects.create(name='Guard Two', slug='guard-two')

    def test_blocks_and_audits_cross_tenant(self):
        from django.core.exceptions import PermissionDenied
        from apps.tenants.guards import guard_tenant
        from apps.tenants.models import CrossTenantAccessAttempt
        from apps.tenants.rls import clear_current_tenant, set_current_tenant
        set_current_tenant(self.t1.id)
        try:
            with self.assertRaises(PermissionDenied):
                guard_tenant(self.t2.id, resource_type='community', resource_id=5)
        finally:
            clear_current_tenant()
        self.assertEqual(
            CrossTenantAccessAttempt.objects.filter(resource_type='community', resource_id='5').count(), 1)

    def test_allows_same_tenant(self):
        from apps.tenants.guards import guard_tenant
        from apps.tenants.models import CrossTenantAccessAttempt
        from apps.tenants.rls import clear_current_tenant, set_current_tenant
        set_current_tenant(self.t1.id)
        try:
            guard_tenant(self.t1.id, resource_type='community', resource_id=9)  # no raise
        finally:
            clear_current_tenant()
        self.assertFalse(CrossTenantAccessAttempt.objects.exists())

    def test_allows_when_no_tenant_pinned(self):
        from apps.tenants.guards import guard_tenant
        from apps.tenants.rls import clear_current_tenant
        clear_current_tenant()
        guard_tenant(self.t2.id, resource_type='community', resource_id=1)  # system context → allowed
