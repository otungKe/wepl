"""
Tests for the double-entry core (Slice 1).

Covered:
  • post_journal posts balanced journals and projects balances correctly
    (debit-normal vs credit-normal accounts).
  • Unbalanced / single-line journals are rejected at the app layer.
  • Idempotency: re-posting a key is a no-op (no double-counting).
  • reverse_journal flips lines and nets balances to zero.
  • trial_balance is always balanced.
  • Projection repair: recompute_account_balance + reconcile_account.
  • Immutability of JournalEntry / JournalLine.
  • Chart-of-Accounts seeding + member sub-ledger resolution.
  • DB-level deferred trigger rejects an unbalanced journal at COMMIT
    (PostgreSQL only).
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.db import IntegrityError, connection, transaction
from django.test import TestCase, TransactionTestCase

from apps.ledger import coa
from apps.ledger.balances import (
    account_balance,
    recompute_account_balance,
    reconcile_account,
    replay_account_balance,
    trial_balance,
)
from apps.ledger.exceptions import JournalImmutableError, UnbalancedJournalError
from apps.ledger.models import Account, AccountBalance, JournalEntry, JournalLine
from apps.ledger.posting import Line, post_journal, reverse_journal

User = get_user_model()

DR = JournalLine.Direction.DEBIT
CR = JournalLine.Direction.CREDIT


class DoubleEntryTests(TestCase):

    def setUp(self):
        self.user = User.objects.create_user(phone_number='+254700000001')
        coa.seed_chart_of_accounts()
        self.float = coa.mpesa_float_account()              # ASSET (debit-normal)
        self.member = coa.member_fund_account(              # LIABILITY (credit-normal)
            user=self.user, fund_type='contribution', fund_id=1,
        )
        self.fee = coa.fee_revenue_account()                # INCOME (credit-normal)

    # ── Posting + projection ────────────────────────────────────────────────
    def test_contribution_posts_balanced_and_projects(self):
        """Member contributes 1,000: DR float / CR member liability."""
        post_journal(
            idempotency_key='contrib-1',
            op_type='CONTRIBUTION',
            lines=[
                Line(self.float,  DR, Decimal('1000')),
                Line(self.member, CR, Decimal('1000')),
            ],
        )
        # Asset increases on debit; liability increases on credit.
        self.assertEqual(account_balance(self.float),  Decimal('1000.0000'))
        self.assertEqual(account_balance(self.member), Decimal('1000.0000'))
        # Projection must equal an independent replay from raw lines.
        self.assertEqual(account_balance(self.float), replay_account_balance(self.float))

    def test_three_line_fee_journal(self):
        """1,020 in, 1,000 to member, 20 fee revenue — the case single-entry can't do."""
        post_journal(
            idempotency_key='contrib-fee-1',
            op_type='CONTRIBUTION',
            lines=[
                Line(self.float,  DR, Decimal('1020')),
                Line(self.member, CR, Decimal('1000')),
                Line(self.fee,    CR, Decimal('20')),
            ],
        )
        self.assertEqual(account_balance(self.float),  Decimal('1020.0000'))
        self.assertEqual(account_balance(self.member), Decimal('1000.0000'))
        self.assertEqual(account_balance(self.fee),    Decimal('20.0000'))
        self.assertTrue(trial_balance()['balanced'])

    # ── Validation ──────────────────────────────────────────────────────────
    def test_unbalanced_journal_rejected(self):
        with self.assertRaises(UnbalancedJournalError):
            post_journal(
                idempotency_key='bad-1',
                op_type='CONTRIBUTION',
                lines=[
                    Line(self.float,  DR, Decimal('1000')),
                    Line(self.member, CR, Decimal('999')),
                ],
            )
        self.assertFalse(JournalEntry.objects.filter(idempotency_key='bad-1').exists())

    def test_single_line_rejected(self):
        with self.assertRaises(UnbalancedJournalError):
            post_journal(
                idempotency_key='bad-2', op_type='CONTRIBUTION',
                lines=[Line(self.float, DR, Decimal('1000'))],
            )

    def test_nonpositive_amount_rejected(self):
        with self.assertRaises(UnbalancedJournalError):
            post_journal(
                idempotency_key='bad-3', op_type='CONTRIBUTION',
                lines=[
                    Line(self.float,  DR, Decimal('0')),
                    Line(self.member, CR, Decimal('0')),
                ],
            )

    # ── Idempotency ─────────────────────────────────────────────────────────
    def test_idempotent_repost_does_not_double_count(self):
        for _ in range(3):
            post_journal(
                idempotency_key='contrib-idem',
                op_type='CONTRIBUTION',
                lines=[
                    Line(self.float,  DR, Decimal('500')),
                    Line(self.member, CR, Decimal('500')),
                ],
            )
        self.assertEqual(JournalEntry.objects.filter(idempotency_key='contrib-idem').count(), 1)
        self.assertEqual(JournalLine.objects.filter(journal__idempotency_key='contrib-idem').count(), 2)
        self.assertEqual(account_balance(self.float), Decimal('500.0000'))

    # ── Reversal ────────────────────────────────────────────────────────────
    def test_reversal_nets_to_zero(self):
        je = post_journal(
            idempotency_key='disb-1', op_type='DISBURSEMENT',
            lines=[
                Line(self.member, DR, Decimal('300')),
                Line(self.float,  CR, Decimal('300')),
            ],
        )
        reverse_journal(je)
        self.assertEqual(account_balance(self.member), Decimal('0.0000'))
        self.assertEqual(account_balance(self.float),  Decimal('0.0000'))
        reversal = JournalEntry.objects.get(reverses=je)
        self.assertEqual(reversal.lines.count(), 2)
        self.assertTrue(trial_balance()['balanced'])

    def test_reversal_is_idempotent(self):
        je = post_journal(
            idempotency_key='disb-2', op_type='DISBURSEMENT',
            lines=[Line(self.member, DR, Decimal('300')), Line(self.float, CR, Decimal('300'))],
        )
        reverse_journal(je)
        reverse_journal(je)  # second call must be a no-op
        self.assertEqual(JournalEntry.objects.filter(reverses=je).count(), 1)
        self.assertEqual(account_balance(self.member), Decimal('0.0000'))

    # ── Projection repair / reconciliation ──────────────────────────────────
    def test_recompute_repairs_drifted_projection(self):
        post_journal(
            idempotency_key='contrib-rec', op_type='CONTRIBUTION',
            lines=[Line(self.float, DR, Decimal('700')), Line(self.member, CR, Decimal('700'))],
        )
        # Corrupt the cache to simulate drift.
        AccountBalance.objects.filter(account=self.float).update(debit_total=Decimal('999999'))
        self.assertFalse(reconcile_account(self.float)['ok'])

        recompute_account_balance(self.float)
        self.assertTrue(reconcile_account(self.float)['ok'])
        self.assertEqual(account_balance(self.float), Decimal('700.0000'))

    # ── Immutability ────────────────────────────────────────────────────────
    def test_journal_entry_is_immutable(self):
        je = post_journal(
            idempotency_key='imm-1', op_type='CONTRIBUTION',
            lines=[Line(self.float, DR, Decimal('10')), Line(self.member, CR, Decimal('10'))],
        )
        je.narration = 'tampered'
        with self.assertRaises(JournalImmutableError):
            je.save()
        with self.assertRaises(JournalImmutableError):
            je.delete()

    def test_journal_line_cannot_be_deleted(self):
        je = post_journal(
            idempotency_key='imm-2', op_type='CONTRIBUTION',
            lines=[Line(self.float, DR, Decimal('10')), Line(self.member, CR, Decimal('10'))],
        )
        with self.assertRaises(JournalImmutableError):
            je.lines.first().delete()

    # ── Chart of Accounts ───────────────────────────────────────────────────
    def test_member_account_resolution_is_idempotent(self):
        a = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=1)
        b = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=1)
        self.assertEqual(a.pk, b.pk)
        self.assertEqual(a.type, Account.Type.LIABILITY)
        # Member sub-ledger now hangs off the pool control account, which hangs
        # off the GL head (ADR-0025 Part B): member → pool → GL.
        self.assertEqual(a.parent.owner_id, None)               # the pool account
        self.assertEqual(a.parent.fund_id, 1)
        self.assertEqual(a.parent.parent.code, coa.MEMBER_CONTRIB_PAYABLE)

    def test_migration_reparents_members_under_pool(self):
        # Mirror the data migration: members parented directly at the GL are
        # re-parented under the new pool control account. (parent is structural —
        # consumed nowhere — so this rewrites no journal.)
        u2 = get_user_model().objects.create_user(phone_number='254799000042')
        gl = coa.gl_account(coa.MEMBER_CONTRIB_PAYABLE)
        m1 = Account.objects.create(code='OLDX-1', name='m', type=Account.Type.LIABILITY,
                                    owner=self.user, fund_type='contribution', fund_id=42, parent=gl)
        m2 = Account.objects.create(code='OLDX-2', name='m', type=Account.Type.LIABILITY,
                                    owner=u2, fund_type='contribution', fund_id=42, parent=gl)
        pool = coa.pool_account(fund_type='contribution', fund_id=42)
        Account.objects.filter(owner__isnull=False, fund_type='contribution', fund_id=42
                               ).exclude(pk=pool.pk).update(parent=pool)
        m1.refresh_from_db(); m2.refresh_from_db()
        self.assertEqual(m1.parent_id, pool.pk)
        self.assertEqual(m2.parent_id, pool.pk)
        self.assertEqual(pool.parent_id, gl.pk)

    def test_pool_account_is_first_class(self):
        pool = coa.pool_account(fund_type='contribution', fund_id=350000)
        self.assertEqual(pool.code, '2000-0350000')
        self.assertIsNone(pool.owner_id)
        self.assertEqual(pool.parent.code, coa.MEMBER_CONTRIB_PAYABLE)
        # Idempotent + race-safe on (fund_type, fund_id).
        self.assertEqual(coa.pool_account(fund_type='contribution', fund_id=350000).pk, pool.pk)
        from django.db import IntegrityError
        with self.assertRaises(IntegrityError):
            Account.objects.create(code='dup-pool', name='dup', type=Account.Type.LIABILITY,
                                   owner=None, fund_type='contribution', fund_id=350000)

    def test_resolution_keys_on_structured_identity_not_code(self):
        # ADR-0025: identity is (owner, fund_type, fund_id), not the code string.
        # Renaming the code must NOT create a second account on next resolve.
        a = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=7)
        Account.objects.filter(pk=a.pk).update(code='ANYTHING-ELSE')
        b = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=7)
        self.assertEqual(a.pk, b.pk)

    def test_every_account_gets_a_uuid7(self):
        a = coa.member_fund_account(user=self.user, fund_type='welfare', fund_id=3)
        self.assertIsNotNone(a.account_uid)
        self.assertEqual(a.account_uid.version, 7)
        gl = coa.mpesa_float_account()
        self.assertIsNotNone(gl.account_uid)
        # Globally unique across GL + sub-ledger.
        self.assertNotEqual(a.account_uid, gl.account_uid)

    def test_duplicate_sub_ledger_is_refused_by_constraint(self):
        coa.member_fund_account(user=self.user, fund_type='shares', fund_id=9)
        with self.assertRaises(IntegrityError):
            Account.objects.create(
                code='dup-shares', name='dup', type=Account.Type.LIABILITY,
                owner=self.user, fund_type='shares', fund_id=9)

    def test_canonical_gl_anchored_code_format(self):
        # ADR-0025: GL-anchored, fixed-width, sortable codes.
        self.assertEqual(coa.pool_code('2000', 1), '2000-0000001')
        self.assertEqual(coa.pool_code('2000', 350000), '2000-0350000')
        a = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=350000)
        self.assertEqual(a.code, f"2000-0350000-{self.user.pk:09d}")
        adv = coa.member_receivable_account(user=self.user, fund_id=14)
        self.assertEqual(adv.code, f"1200-0000014-{self.user.pk:09d}")

    def test_seed_is_idempotent(self):
        before = Account.objects.count()
        coa.seed_chart_of_accounts()
        self.assertEqual(Account.objects.count(), before)


class DeferredTriggerTests(TransactionTestCase):
    """
    The DB trigger fires at COMMIT, so we need real commits (TransactionTestCase),
    not the wrapping transaction of TestCase. PostgreSQL only.
    """

    def setUp(self):
        if connection.vendor != 'postgresql':
            self.skipTest('Deferred balance trigger is PostgreSQL-specific.')
        self.user = User.objects.create_user(phone_number='+254700000099')
        coa.seed_chart_of_accounts()
        self.float = coa.mpesa_float_account()
        self.member = coa.member_fund_account(user=self.user, fund_type='contribution', fund_id=1)

    def test_db_rejects_unbalanced_journal_at_commit(self):
        """Bypass the writer and write an unbalanced journal directly — COMMIT must fail."""
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                je = JournalEntry(idempotency_key='raw-bad', op_type='CONTRIBUTION')
                je.save()  # fresh insert — immutability guard only blocks updates
                JournalLine.objects.bulk_create([
                    JournalLine(journal=je, account=self.float,  direction=DR, amount=Decimal('100')),
                    JournalLine(journal=je, account=self.member, direction=CR, amount=Decimal('80')),
                ])
                # leaving the atomic block triggers the deferred constraint check
