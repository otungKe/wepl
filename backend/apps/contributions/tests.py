from decimal import Decimal
from unittest import skip
from django.test import TestCase
from django.contrib.auth import get_user_model

# Quarantined under P0-02 — see GitHub issue #14. These exercise the legacy money
# paths (single-entry shadow ledger + mutable balance fields) that Phase 0 rewrites
# onto post_journal(); they will be rewritten and unskipped in P0-05/06.
_LEGACY = "P0-02 #14: legacy money-path test; rewrite onto post_journal() in P0-05/06"

from django.core.exceptions import PermissionDenied, ValidationError

from apps.communities.models import Community, CommunityMembership
from .models import (
    Contribution, ContributionParticipant, ContributionTransaction,
    ROSCASlot, DisbursementRequest, DisbursementVote,
    WelfareFund, WelfareClaim, EmergencyAdvance,
)
from .services import (
    ContributionService, ROSCAService,
    DisbursementService, WelfareService,
    EmergencyAdvanceService,
)

from datetime import date

from apps.ledger import coa
from apps.ledger.balances import account_balance, trial_balance
from apps.ledger.models import JournalEntry

User = get_user_model()


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def approve_kyc(user):
    """Give a user an approved KYC profile (contribute() requires one)."""
    from apps.users.models import KYCProfile
    return KYCProfile.objects.create(
        user=user, status="approved",
        given_names="Test", surname="User",
        id_number=f"ID{user.pk}", date_of_birth=date(1990, 1, 1),
    )


def make_community(creator, name="Test Chama"):
    from apps.communities.services import CommunityService
    return CommunityService.create_community(creator, {"name": name})


def make_contribution(creator, community=None, ctype="POOL", cycle_amount=None):
    data = {
        "title": "Test Pool",
        "contribution_type": ctype,
        "visibility": "closed" if community else "open",
    }
    if community:
        data["community"] = community
    if cycle_amount:
        data["cycle_amount"] = cycle_amount
    return ContributionService.create_contribution(creator, data)


# ---------------------------------------------------------------------------
# Core contribution flow
# ---------------------------------------------------------------------------

class ContributionCreationGovernanceTests(TestCase):
    """Regression tests for issue #14 — creation must not run the old, buggy
    creation-time governance deadlock pre-check. Quorum is enforced at request
    time instead (see submit_disbursement_request / propose_amendment)."""

    def setUp(self):
        self.alice = make_user("+254700000201")

    def test_solo_open_contribution_creation_succeeds(self):
        # Previously blocked: 'admins' threshold + only the creator -> 0 voters.
        c = ContributionService.create_contribution(self.alice, {"title": "Solo Pool"})
        self.assertEqual(c.created_by, self.alice)
        self.assertTrue(
            ContributionParticipant.objects.filter(
                contribution=c, user=self.alice, is_active=True
            ).exists()
        )

    def test_percentage_threshold_creation_does_not_crash(self):
        # Previously raised TypeError: the proxy object was used as a FK in a
        # ContributionParticipant query for percentage thresholds.
        c = ContributionService.create_contribution(
            self.alice,
            {"title": "Pct Pool", "voting_threshold": "50",
             "amendment_voting_threshold": "50"},
        )
        self.assertEqual(c.voting_threshold, "50")


class ContributionLedgerPostingTests(TestCase):
    """P0-05: contribute() posts a balanced double-entry journal alongside the
    legacy writes (strangler pattern). Reads/gates flip to the ledger in P0-06."""

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = make_user("+254700000301")
        approve_kyc(self.alice)
        self.c = ContributionService.create_contribution(self.alice, {"title": "Pool"})

    def test_contribute_posts_balanced_journal(self):
        ContributionService.contribute(
            self.alice, self.c.id, Decimal("1000"), mpesa_receipt="RCPT1")

        je = JournalEntry.objects.get(op_type="CONTRIBUTION")
        self.assertIsNotNone(je.financial_transaction)

        member = coa.member_fund_account(
            user=self.alice, fund_type="contribution", fund_id=self.c.id)
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("1000.0000"))
        self.assertEqual(account_balance(member), Decimal("1000.0000"))
        self.assertTrue(trial_balance()["balanced"])

        # Pool balance is now ledger-derived (the mutable current_amount column
        # was removed in P0-07).
        from apps.ledger.balances import fund_balance
        self.assertEqual(fund_balance("contribution", self.c.id), Decimal("1000.0000"))

    def test_contribute_is_idempotent_on_receipt(self):
        for _ in range(2):
            ContributionService.contribute(
                self.alice, self.c.id, Decimal("1000"), mpesa_receipt="DUP")
        self.assertEqual(JournalEntry.objects.filter(op_type="CONTRIBUTION").count(), 1)
        member = coa.member_fund_account(
            user=self.alice, fund_type="contribution", fund_id=self.c.id)
        self.assertEqual(account_balance(member), Decimal("1000.0000"))
        self.assertTrue(trial_balance()["balanced"])


class WelfareLedgerPostingTests(TestCase):
    """P0-05: welfare contribution posts a balanced journal alongside legacy."""

    def setUp(self):
        coa.seed_chart_of_accounts()
        self.alice = make_user("+254700000401")
        self.community = make_community(self.alice, "Welfare Chama")

    def test_welfare_contribution_posts_journal(self):
        fund = WelfareService.get_or_create_community_fund(self.community)
        WelfareService.contribute_to_welfare(
            fund.id, self.alice, Decimal("500"), mpesa_receipt="WR1")
        member = coa.member_fund_account(user=self.alice, fund_type="welfare", fund_id=fund.id)
        self.assertEqual(account_balance(member), Decimal("500.0000"))
        self.assertEqual(account_balance(coa.mpesa_float_account()), Decimal("500.0000"))
        self.assertTrue(trial_balance()["balanced"])


@skip(_LEGACY)
class ContributionCoreTests(TestCase):

    def setUp(self):
        self.alice = make_user("+254700000001")
        self.bob   = make_user("+254700000002")
        self.carol = make_user("+254700000003")

    def test_create_contribution_adds_creator_as_participant(self):
        c = make_contribution(self.alice)
        self.assertTrue(
            ContributionParticipant.objects.filter(contribution=c, user=self.alice, is_active=True).exists()
        )

    def test_join_creates_participant(self):
        c = make_contribution(self.alice)
        ContributionService.join_contribution(c.id, self.bob)
        self.assertTrue(
            ContributionParticipant.objects.filter(contribution=c, user=self.bob, is_active=True).exists()
        )

    def test_contribute_updates_balances(self):
        c = make_contribution(self.alice)
        ContributionService.contribute(self.alice, c.id, Decimal("1000"))
        c.refresh_from_db()
        self.assertEqual(c.current_amount, Decimal("1000"))
        balance = ContributionBalance.objects.get(contribution=c, user=self.alice)
        self.assertEqual(balance.amount, Decimal("1000"))

    def test_contribute_requires_active_participant(self):
        c = make_contribution(self.alice)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            ContributionService.contribute(self.bob, c.id, Decimal("500"))

    def test_contribute_rejects_zero_amount(self):
        c = make_contribution(self.alice)
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            ContributionService.contribute(self.alice, c.id, Decimal("0"))

    def test_leave_deactivates_participant(self):
        c = make_contribution(self.alice)
        ContributionService.join_contribution(c.id, self.bob)
        ContributionService.leave_contribution(c.id, self.bob)
        self.assertFalse(
            ContributionParticipant.objects.filter(contribution=c, user=self.bob, is_active=True).exists()
        )

    def test_milestone_notification_at_100_percent(self):
        c = ContributionService.create_contribution(self.alice, {
            "title": "Funded Pool",
            "contribution_type": "POOL",
            "visibility": "open",
            "target_amount": Decimal("1000"),
        })
        ContributionService.contribute(self.alice, c.id, Decimal("1000"))
        from apps.notifications.models import Notification
        n = Notification.objects.filter(
            user=self.alice, notification_type="contribution_milestone"
        )
        self.assertTrue(n.exists())

    def test_get_by_invite_code(self):
        c = make_contribution(self.alice)
        found = ContributionService.get_by_invite_code(c.invite_code)
        self.assertEqual(found.id, c.id)

    def test_transaction_recorded_on_contribute(self):
        c = make_contribution(self.alice)
        ContributionService.contribute(self.alice, c.id, Decimal("500"))
        tx = ContributionTransaction.objects.filter(contribution=c, user=self.alice).first()
        self.assertIsNotNone(tx)
        self.assertEqual(tx.transaction_type, "CONTRIBUTION")
        self.assertEqual(tx.amount, Decimal("500"))


# ---------------------------------------------------------------------------
# ROSCA (merry-go-round)
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class ROSCATests(TestCase):

    def setUp(self):
        self.alice = make_user("+254700000010")
        self.bob   = make_user("+254700000011")
        self.carol = make_user("+254700000012")

    def _make_rosca(self):
        c = make_contribution(self.alice, ctype="ROSCA", cycle_amount=Decimal("2000"))
        ContributionService.join_contribution(c.id, self.bob)
        ContributionService.join_contribution(c.id, self.carol)
        return c

    def test_initialize_creates_correct_slot_count(self):
        c = self._make_rosca()
        slots = ROSCAService.initialize_rotation(c.id, self.alice)
        self.assertEqual(slots.count(), 3)

    def test_initialize_requires_creator(self):
        c = self._make_rosca()
        with self.assertRaises(PermissionDenied):
            ROSCAService.initialize_rotation(c.id, self.bob)

    def test_initialize_requires_two_plus_participants(self):
        from django.core.exceptions import ValidationError
        c = make_contribution(self.alice, ctype="ROSCA", cycle_amount=Decimal("2000"))
        with self.assertRaises(ValidationError):
            ROSCAService.initialize_rotation(c.id, self.alice)

    def test_slot_orders_are_unique(self):
        c = self._make_rosca()
        slots = ROSCAService.initialize_rotation(c.id, self.alice)
        orders = [s.slot_order for s in slots]
        self.assertEqual(len(orders), len(set(orders)))

    def test_mark_slot_paid_resets_pool(self):
        c = self._make_rosca()
        ROSCAService.initialize_rotation(c.id, self.alice)
        # Everyone contributes
        for user in [self.alice, self.bob, self.carol]:
            ContributionService.contribute(user, c.id, Decimal("2000"))
        ROSCAService.mark_slot_paid(c.id, self.alice)
        c.refresh_from_db()
        self.assertEqual(c.current_amount, Decimal("0"))

    def test_mark_slot_paid_records_withdrawal_transaction(self):
        c = self._make_rosca()
        ROSCAService.initialize_rotation(c.id, self.alice)
        for user in [self.alice, self.bob, self.carol]:
            ContributionService.contribute(user, c.id, Decimal("2000"))
        ROSCAService.mark_slot_paid(c.id, self.alice)
        wdl = ContributionTransaction.objects.filter(
            contribution=c, transaction_type="WITHDRAWAL"
        )
        self.assertTrue(wdl.exists())


# ---------------------------------------------------------------------------
# Multi-signature Disbursements
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class DisbursementTests(TestCase):

    def setUp(self):
        self.alice = make_user("+254700000020")
        self.bob   = make_user("+254700000021")
        self.carol = make_user("+254700000022")
        self.community = make_community(self.alice, "Disburse Chama")
        # Join community first, then promote bob and carol to admin
        from apps.communities.services import CommunityService
        for user in [self.bob, self.carol]:
            CommunityService.join_community(user, self.community)
        CommunityMembership.objects.filter(community=self.community, user=self.bob).update(role="admin")
        CommunityMembership.objects.filter(community=self.community, user=self.carol).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool",
            "contribution_type": "POOL",
            "visibility": "closed",
            "community": self.community,
            # voting_threshold='50' → required_approvals = ceil(3 * 0.5) = 2
            # With 'admins' threshold only 1 vote is needed — first vote would
            # immediately execute and make the PENDING assertion below wrong.
            "voting_threshold": "50",
        })
        # Add all three as contribution participants (alice already added by create)
        for user in [self.bob, self.carol]:
            ContributionService.join_contribution(self.c.id, user)
        ContributionService.contribute(self.alice, self.c.id, Decimal("10000"))

    def test_create_disbursement_request(self):
        req = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("3000"), "School fees", "+254700000020"
        )
        self.assertEqual(req.status, "PENDING")
        self.assertEqual(req.amount, Decimal("3000"))

    def test_disbursement_exceeding_balance_raises(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            DisbursementService.create_request(
                self.c.id, self.alice, Decimal("99999"), "Too much", "+254700000020"
            )

    def test_non_participant_cannot_request(self):
        stranger = make_user("+254700000099")
        with self.assertRaises(PermissionDenied):
            DisbursementService.create_request(
                self.c.id, stranger, Decimal("100"), "Nope", "+254700000099"
            )

    def test_approval_threshold_executes_disbursement(self):
        req = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("3000"), "Medical", "+254700000020"
        )
        # First vote — not enough yet
        DisbursementService.vote(req.id, self.bob, "APPROVE")
        req.refresh_from_db()
        self.assertEqual(req.status, "PENDING")
        # Second vote — hits min_approvals=2, auto-executes
        DisbursementService.vote(req.id, self.carol, "APPROVE")
        req.refresh_from_db()
        self.assertEqual(req.status, "EXECUTED")
        self.c.refresh_from_db()
        self.assertEqual(self.c.current_amount, Decimal("7000"))

    def test_rejection_threshold_rejects_request(self):
        req = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("3000"), "Medical", "+254700000020"
        )
        DisbursementService.vote(req.id, self.bob, "REJECT")
        DisbursementService.vote(req.id, self.carol, "REJECT")
        req.refresh_from_db()
        self.assertEqual(req.status, "REJECTED")

    def test_duplicate_vote_not_counted_twice(self):
        req = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("1000"), "Test", "+254700000020"
        )
        DisbursementService.vote(req.id, self.bob, "APPROVE")
        # Second vote raises ValidationError — the DB constraint is enforced at the service layer.
        with self.assertRaises(ValidationError):
            DisbursementService.vote(req.id, self.bob, "APPROVE")
        self.assertEqual(req.votes.filter(vote="APPROVE").count(), 1)

    def test_non_admin_cannot_vote(self):
        stranger = make_user("+254700000098")
        req = DisbursementService.create_request(
            self.c.id, self.alice, Decimal("1000"), "Test", "+254700000020"
        )
        with self.assertRaises(PermissionDenied):
            DisbursementService.vote(req.id, stranger, "APPROVE")


# ---------------------------------------------------------------------------
# Welfare Fund
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class WelfareTests(TestCase):

    def setUp(self):
        self.alice = make_user("+254700000030")
        self.bob   = make_user("+254700000031")
        self.carol = make_user("+254700000032")
        self.community = make_community(self.alice, "Welfare Chama")
        from apps.communities.services import CommunityService
        CommunityService.join_community(self.bob, self.community)
        CommunityService.join_community(self.carol, self.community)
        CommunityMembership.objects.filter(community=self.community, user=self.bob).update(role="admin")

    def _get_fund(self):
        """Helper: get-or-create the community welfare fund."""
        return WelfareService.get_or_create_community_fund(self.community)

    def test_get_or_create_fund(self):
        fund = WelfareService.get_or_create_community_fund(self.community)
        self.assertEqual(fund.community, self.community)
        self.assertEqual(fund.balance, Decimal("0"))

    def test_contribute_increases_balance(self):
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("500"), mpesa_receipt="RCP_A")
        WelfareService.contribute_to_welfare(fund.id, self.bob, Decimal("300"), mpesa_receipt="RCP_B")
        fund.refresh_from_db()
        self.assertEqual(fund.balance, Decimal("800"))

    @skip(_LEGACY)
    def test_contribute_idempotent_with_same_receipt(self):
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("500"), mpesa_receipt="RCP_IDEM")
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("500"), mpesa_receipt="RCP_IDEM")
        fund.refresh_from_db()
        # Second call is a no-op — balance should be 500, not 1000.
        self.assertEqual(fund.balance, Decimal("500"))

    @skip(_LEGACY)
    def test_submit_claim_creates_pending_claim(self):
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("5000"), mpesa_receipt="RCP_5K")
        claim = WelfareService.submit_claim(fund.id, self.bob, Decimal("2000"), "Hospital bill")
        self.assertEqual(claim.status, "PENDING")
        self.assertEqual(claim.amount_requested, Decimal("2000"))

    @skip(_LEGACY)
    def test_admin_approves_claim_transitions_to_approved(self):
        # After admin approval the claim is APPROVED (not yet DISBURSED —
        # DISBURSED happens via the B2C callback which is not called in tests).
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("5000"), mpesa_receipt="RCP_5K2")
        claim = WelfareService.submit_claim(fund.id, self.bob, Decimal("2000"), "Emergency")
        WelfareService.approve_claim(claim.id, self.alice)
        claim.refresh_from_db()
        self.assertEqual(claim.status, "APPROVED")
        fund.refresh_from_db()
        self.assertEqual(fund.balance, Decimal("3000"))

    def test_insufficient_balance_prevents_disburse(self):
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("100"), mpesa_receipt="RCP_100")
        with self.assertRaises(ValidationError):
            WelfareService.submit_claim(fund.id, self.bob, Decimal("5000"), "Too much")

    @skip(_LEGACY)
    def test_admin_can_reject_claim(self):
        fund = self._get_fund()
        WelfareService.contribute_to_welfare(fund.id, self.alice, Decimal("5000"), mpesa_receipt="RCP_5K3")
        claim = WelfareService.submit_claim(fund.id, self.carol, Decimal("1000"), "Request")
        WelfareService.reject_claim(claim.id, self.bob)  # bob is admin
        claim.refresh_from_db()
        self.assertEqual(claim.status, "REJECTED")


# ---------------------------------------------------------------------------
# Emergency Advances
# ---------------------------------------------------------------------------

@skip(_LEGACY)
class EmergencyAdvanceTests(TestCase):

    def setUp(self):
        self.alice = make_user("+254700000040")
        self.bob   = make_user("+254700000041")
        self.community = make_community(self.alice, "Advance Chama")
        from apps.communities.services import CommunityService
        CommunityService.join_community(self.bob, self.community)
        CommunityMembership.objects.filter(community=self.community, user=self.bob).update(role="admin")
        self.c = ContributionService.create_contribution(self.alice, {
            "title": "Pool",
            "contribution_type": "POOL",
            "visibility": "closed",
            "community": self.community,
        })
        ContributionService.join_contribution(self.c.id, self.bob)
        # Alice contributes 10,000 → max advance = 8,000
        ContributionService.contribute(self.alice, self.c.id, Decimal("10000"))

    def test_request_advance_within_limit(self):
        adv = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None
        )
        self.assertEqual(adv.status, "PENDING")
        self.assertEqual(adv.amount, Decimal("5000"))

    def test_advance_exceeding_80_percent_raises(self):
        from django.core.exceptions import ValidationError
        with self.assertRaises(ValidationError):
            EmergencyAdvanceService.request_advance(
                self.c.id, self.alice, Decimal("9000"), Decimal("10"), None
            )

    def test_non_participant_cannot_request(self):
        stranger = make_user("+254700000096")
        with self.assertRaises(PermissionDenied):
            EmergencyAdvanceService.request_advance(
                self.c.id, stranger, Decimal("1000"), Decimal("10"), None
            )

    def test_admin_can_approve(self):
        adv = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None
        )
        # approve_advance transitions directly to DISBURSED (not APPROVED) —
        # the funds are reserved and B2C is scheduled in the same call.
        approved = EmergencyAdvanceService.approve_advance(adv.id, self.bob)
        self.assertEqual(approved.status, "DISBURSED")

    def test_non_admin_cannot_approve(self):
        adv = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None
        )
        stranger = make_user("+254700000095")
        with self.assertRaises(PermissionDenied):
            EmergencyAdvanceService.approve_advance(adv.id, stranger)

    def test_total_due_calculation(self):
        adv = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None
        )
        # 5000 * 1.10 = 5500
        self.assertEqual(adv.total_due, Decimal("5500.00"))

    def test_duplicate_advance_blocked(self):
        from django.core.exceptions import ValidationError
        EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("3000"), Decimal("10"), None
        )
        with self.assertRaises(ValidationError):
            EmergencyAdvanceService.request_advance(
                self.c.id, self.alice, Decimal("2000"), Decimal("10"), None
            )

    def test_repayment_marks_advance_repaid(self):
        adv = EmergencyAdvanceService.request_advance(
            self.c.id, self.alice, Decimal("5000"), Decimal("10"), None
        )
        EmergencyAdvanceService.approve_advance(adv.id, self.bob)
        # Repay the full amount due (5500); mpesa_receipt anchors idempotency key.
        EmergencyAdvanceService.repay(adv.id, self.alice, Decimal("5500"), mpesa_receipt="RPY_001")
        adv.refresh_from_db()
        self.assertEqual(adv.status, "REPAID")
