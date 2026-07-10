from rest_framework import serializers

from apps.ledger.balances import fund_balance, member_fund_balance

from .models import (
    Contribution, ContributionParticipant, ContributionTransaction,
    ROSCASlot, DisbursementRequest, DisbursementVote,
    SharesFund, ShareHolding,
    WelfareFund, WelfareContribution, WelfareClaim, WelfareVote,
    EmergencyAdvance,
    StandingOrder, StandingOrderSlot,
    ContributionAmendment, ContributionAmendmentVote,
    ContributionJoinRequest,
)


class ContributionSerializer(serializers.ModelSerializer):
    created_by        = serializers.CharField(source='created_by.phone_number', read_only=True)
    participant_count = serializers.SerializerMethodField()
    # Ledger-derived pool balance (replaces the removed mutable current_amount column)
    current_amount    = serializers.SerializerMethodField()
    user_balance      = serializers.SerializerMethodField()
    voting_label      = serializers.SerializerMethodField()
    my_rosca_slot     = serializers.SerializerMethodField()
    # Plain CharField so custom numeric percentages (e.g. '75') pass validation
    voting_threshold  = serializers.CharField(required=False, default='admins')
    # Whether the requesting user has admin rights on this contribution
    is_admin          = serializers.SerializerMethodField()
    # Whether the requesting user is already in this contribution (creator or
    # active participant) — authoritative, so clients don't string-match phones.
    is_participant    = serializers.SerializerMethodField()

    class Meta:
        model = Contribution
        fields = [
            'id', 'title', 'description', 'visibility',
            'created_by', 'community', 'invite_code',
            'target_amount', 'current_amount', 'member_target_amount',
            'tenure_type', 'end_date', 'period_months',
            'transaction_visibility', 'amendment_proposer',
            'amendment_voting_threshold',
            'late_contribution_policy', 'late_contribution_grace_days',
            'frequency', 'amount_type', 'fixed_amount',
            'voting_threshold', 'voting_label',
            'min_approvals', 'is_active', 'status', 'is_campaign',
            'participant_count', 'user_balance', 'my_rosca_slot',
            'is_admin', 'is_participant', 'created_at',
        ]
        extra_kwargs = {
            'invite_code':    {'read_only': True},
        }

    def get_current_amount(self, obj):
        return str(fund_balance('contribution', obj.id))

    def get_participant_count(self, obj):
        # Use annotation if present (injected by list views via annotate())
        annotated = getattr(obj, 'active_participant_count', None)
        if annotated is not None:
            return annotated
        return obj.participants.filter(is_active=True).count()

    def get_user_balance(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        # List views inject a {contribution_id: balance} dict via context to avoid
        # N+1; detail views fall back to a single read.
        bulk = self.context.get('user_balances')
        if bulk is not None:
            return str(bulk.get(obj.id, '0'))
        return str(member_fund_balance(request.user, 'contribution', obj.id))

    def get_voting_label(self, obj):
        labels = {
            'admins': 'Admins only',
            '50':     '50%+1 majority',
            '100':    'All members',
        }
        if obj.voting_threshold in labels:
            return labels[obj.voting_threshold]
        # Custom numeric percentage
        try:
            pct = int(obj.voting_threshold)
            return f'{pct}% of members'
        except (ValueError, TypeError):
            return obj.voting_threshold

    def get_my_rosca_slot(self, obj):
        """
        Returns the current user's ROSCA rotation slot so the mobile client can
        show "Your turn: Slot 3 · Expected KES 4,500" without a separate API call.
        Returns None when no ROSCA rotation has been set up (Issue 13).
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return None
        try:
            slot = (
                obj.rosca_slots
                .select_related('participant__user')
                .filter(participant__user=request.user)
                .order_by('cycle_number', 'slot_order')
                .first()
            )
            if slot is None:
                return None
            return {
                'slot_order':    slot.slot_order,
                'cycle_number':  slot.cycle_number,
                'has_received':  slot.has_received,
                'payout_amount': str(slot.payout_amount) if slot.payout_amount else None,
                'received_at':   slot.received_at.isoformat() if slot.received_at else None,
            }
        except Exception:
            return None

    def get_is_admin(self, obj):
        """True if the requesting user is the creator OR a community admin/treasurer."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        from apps.ledger.permissions import FinancialPermissions
        return FinancialPermissions.is_contribution_admin(obj, request.user)

    def get_is_participant(self, obj):
        """True if the requesting user is the creator OR an active participant."""
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        if obj.created_by_id == request.user.id:
            return True
        return obj.participants.filter(user=request.user, is_active=True).exists()

    def validate(self, attrs):
        # For partial updates fall back to the existing instance values so that
        # cross-field rules don't fire when only cosmetic fields (title/description)
        # are being patched.
        inst = self.instance
        visibility    = attrs.get('visibility',    inst.visibility    if inst else 'closed')
        community     = attrs.get('community',     inst.community     if inst else None)
        tenure_type   = attrs.get('tenure_type',   inst.tenure_type   if inst else 'open')
        end_date      = attrs.get('end_date',      inst.end_date      if inst else None)
        period_months = attrs.get('period_months', inst.period_months if inst else None)
        amount_type   = attrs.get('amount_type',   inst.amount_type   if inst else 'open')
        fixed_amount  = attrs.get('fixed_amount',  inst.fixed_amount  if inst else None)

        if visibility == 'closed' and not community:
            raise serializers.ValidationError(
                {'community': 'A closed contribution must be tied to a community.'}
            )
        if tenure_type == 'date' and not end_date:
            raise serializers.ValidationError({'end_date': 'Required when tenure is "date".'})
        if tenure_type == 'period' and not period_months:
            raise serializers.ValidationError({'period_months': 'Required when tenure is "period".'})
        if amount_type == 'fixed' and not fixed_amount:
            raise serializers.ValidationError({'fixed_amount': 'Required when amount type is "fixed".'})
        return attrs


class ContributionParticipantSerializer(serializers.ModelSerializer):
    phone_number   = serializers.CharField(source='user.phone_number', read_only=True)
    name           = serializers.SerializerMethodField()
    balance        = serializers.SerializerMethodField()
    progress_pct   = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.user.name or None

    def _member_balance(self, obj):
        # Views may inject {user_id: balance} via context to avoid N+1.
        bulk = self.context.get('member_balances')
        if bulk is not None:
            return bulk.get(obj.user_id, 0)
        return member_fund_balance(obj.user, 'contribution', obj.contribution_id)

    def get_balance(self, obj):
        """How much this member has contributed to this contribution so far."""
        return str(self._member_balance(obj))

    def get_progress_pct(self, obj):
        """
        Percentage of member_target_amount reached by this member.
        Returns None if the contribution has no member_target_amount.
        """
        target = obj.contribution.member_target_amount
        if not target or target <= 0:
            return None
        return round(float(self._member_balance(obj)) / float(target) * 100, 1)

    class Meta:
        model = ContributionParticipant
        fields = ['id', 'phone_number', 'name', 'is_active', 'balance', 'progress_pct']


class ContributionPaymentSerializer(serializers.Serializer):
    contribution_id = serializers.IntegerField()
    amount          = serializers.DecimalField(max_digits=12, decimal_places=2)


class ContributionTransactionSerializer(serializers.ModelSerializer):
    phone_number       = serializers.CharField(source='user.phone_number', read_only=True)
    name               = serializers.SerializerMethodField()
    contribution_title = serializers.CharField(source='contribution.title', read_only=True)
    platform_ref       = serializers.SerializerMethodField()

    class Meta:
        model = ContributionTransaction
        fields = [
            'id', 'phone_number', 'name', 'contribution', 'contribution_title',
            'amount', 'transaction_type', 'note',
            'mpesa_receipt', 'platform_ref',
            'created_at',
        ]

    def get_name(self, obj):
        return obj.user.name or None

    def get_platform_ref(self, obj):
        # Prefer the ledger movement's reference (the book of record) so members
        # and ops quote the same handle. The FK id is on the row — no extra query.
        if obj.financial_transaction_id:
            return f"WEPL-TXN-{obj.financial_transaction_id:06d}"
        return f"WEPL-TXN-{obj.id:06d}"


# ---------------------------------------------------------------------------
# Shares Fund
# ---------------------------------------------------------------------------

class ShareHoldingSerializer(serializers.ModelSerializer):
    phone_number  = serializers.CharField(source='user.phone_number', read_only=True)
    name          = serializers.CharField(source='user.name', read_only=True)
    ownership_pct = serializers.DecimalField(max_digits=6, decimal_places=2, read_only=True)

    class Meta:
        model = ShareHolding
        fields = ['id', 'phone_number', 'name', 'shares_count', 'total_contributed', 'ownership_pct']


class SharesFundSerializer(serializers.ModelSerializer):
    holdings     = ShareHoldingSerializer(many=True, read_only=True)
    total_shares = serializers.SerializerMethodField()
    # Ledger-derived (replaces the removed mutable total_pool column)
    total_pool   = serializers.SerializerMethodField()

    class Meta:
        model = SharesFund
        fields = ['id', 'community', 'name', 'share_price', 'total_pool', 'total_shares', 'holdings', 'created_at']

    def get_total_pool(self, obj):
        return str(fund_balance('shares', obj.id))

    def get_total_shares(self, obj):
        from django.db.models import Sum
        result = obj.holdings.aggregate(total=Sum('shares_count'))
        return str(result['total'] or 0)


# ---------------------------------------------------------------------------
# ROSCA
# ---------------------------------------------------------------------------

class ROSCASlotSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='participant.user.phone_number', read_only=True)

    class Meta:
        model = ROSCASlot
        fields = ['id', 'slot_order', 'cycle_number', 'phone_number', 'has_received', 'received_at', 'payout_amount']


# ---------------------------------------------------------------------------
# Disbursement
# ---------------------------------------------------------------------------

class DisbursementVoteSerializer(serializers.ModelSerializer):
    voter_phone = serializers.CharField(source='voter.phone_number', read_only=True)

    class Meta:
        model = DisbursementVote
        fields = ['id', 'voter_phone', 'vote', 'voted_at']


class DisbursementRequestSerializer(serializers.ModelSerializer):
    requested_by_phone = serializers.CharField(source='requested_by.phone_number', read_only=True)
    votes              = DisbursementVoteSerializer(many=True, read_only=True)
    approve_count      = serializers.IntegerField(read_only=True)
    reject_count       = serializers.IntegerField(read_only=True)
    required_approvals = serializers.SerializerMethodField()
    # Payout target is a counterparty phone shown to the whole group — mask it for
    # members (operators see the full number in the ops console). Writable on
    # create via recipient_phone (below); this read-only field is the masked view.
    recipient_phone    = serializers.SerializerMethodField()

    class Meta:
        model = DisbursementRequest
        fields = [
            'id', 'contribution', 'requested_by_phone', 'amount', 'reason',
            'recipient_phone', 'status', 'approve_count', 'reject_count',
            'required_approvals', 'votes', 'created_at', 'executed_at',
        ]
        read_only_fields = ['status', 'approve_count', 'reject_count', 'required_approvals', 'votes', 'executed_at']

    def get_recipient_phone(self, obj):
        from apps.users.phone import mask_phone
        return mask_phone(obj.recipient_phone)

    def get_required_approvals(self, obj):
        return obj.contribution.required_approvals()


# ---------------------------------------------------------------------------
# Welfare
# ---------------------------------------------------------------------------

class WelfareFundSerializer(serializers.ModelSerializer):
    is_admin = serializers.SerializerMethodField()
    # Ledger-derived (replaces the removed mutable balance column)
    balance  = serializers.SerializerMethodField()

    def get_balance(self, obj):
        return str(fund_balance('welfare', obj.id))

    def get_is_admin(self, obj):
        """
        True if the requesting user is an admin or treasurer of the fund's
        community. Used by the mobile client to show/hide admin controls
        without relying on spoofable URL params (Issue 07).
        """
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return False
        if not obj.community:
            return False
        community = obj.community
        user = request.user
        return (
            community.admin_id == user.pk
            or community.treasurers.filter(pk=user.pk).exists()
            or community.memberships.filter(user=user, is_admin=True).exists()
        )

    class Meta:
        model = WelfareFund
        fields = ['id', 'community', 'name', 'balance', 'monthly_contribution', 'created_at', 'is_admin']


class WelfareContributionSerializer(serializers.ModelSerializer):
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)

    class Meta:
        model = WelfareContribution
        fields = ['id', 'phone_number', 'amount', 'created_at']


class WelfareVoteSerializer(serializers.ModelSerializer):
    voter_phone = serializers.CharField(source='voter.phone_number', read_only=True)

    class Meta:
        model = WelfareVote
        fields = ['id', 'voter_phone', 'vote', 'voted_at']


class WelfareClaimSerializer(serializers.ModelSerializer):
    claimant_phone = serializers.CharField(source='claimant.phone_number', read_only=True)
    votes          = WelfareVoteSerializer(many=True, read_only=True)
    approve_count  = serializers.IntegerField(read_only=True)

    class Meta:
        model = WelfareClaim
        fields = [
            'id', 'fund', 'claimant_phone', 'amount_requested', 'reason',
            'status', 'approve_count', 'votes', 'created_at',
            'approved_at', 'disbursed_at', 'mpesa_receipt',
        ]
        read_only_fields = ['status', 'approve_count', 'votes', 'approved_at', 'disbursed_at', 'mpesa_receipt']


# ---------------------------------------------------------------------------
# Emergency Advance
# ---------------------------------------------------------------------------

class EmergencyAdvanceSerializer(serializers.ModelSerializer):
    borrower_phone = serializers.CharField(source='borrower.phone_number', read_only=True)
    total_due      = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)
    balance_due    = serializers.DecimalField(max_digits=12, decimal_places=2, read_only=True)

    class Meta:
        model = EmergencyAdvance
        fields = [
            'id', 'contribution', 'borrower_phone', 'amount', 'interest_rate',
            'status', 'amount_repaid', 'total_due', 'balance_due',
            'repayment_due', 'created_at',
        ]
        read_only_fields = ['status', 'amount_repaid', 'total_due', 'balance_due']


class StandingOrderSlotSerializer(serializers.ModelSerializer):
    class Meta:
        model  = StandingOrderSlot
        fields = ['id', 'slot_order', 'phone_number', 'name', 'has_received', 'received_at']


class StandingOrderSerializer(serializers.ModelSerializer):
    slots            = StandingOrderSlotSerializer(many=True, read_only=True)
    created_by_phone = serializers.CharField(source='created_by.phone_number', read_only=True)
    next_slot        = serializers.SerializerMethodField()

    class Meta:
        model  = StandingOrder
        fields = [
            'id', 'contribution', 'created_by_phone',
            'amount', 'frequency', 'payee_type', 'fixed_payee_phone',
            'is_active', 'slots', 'next_slot', 'created_at',
        ]
        read_only_fields = ['created_by_phone', 'slots', 'next_slot']

    def get_next_slot(self, obj):
        if obj.payee_type != 'rotating':
            return None
        slot = obj.slots.filter(has_received=False).first()
        if not slot:
            return None
        return StandingOrderSlotSerializer(slot).data


# ---------------------------------------------------------------------------
# Contribution Amendments
# ---------------------------------------------------------------------------

class ContributionAmendmentVoteSerializer(serializers.ModelSerializer):
    voter_phone = serializers.CharField(source='voter.phone_number', read_only=True)
    voter_name  = serializers.SerializerMethodField()

    class Meta:
        model  = ContributionAmendmentVote
        fields = ['id', 'voter_phone', 'voter_name', 'vote', 'voted_at']

    def get_voter_name(self, obj):
        return obj.voter.name or obj.voter.phone_number


class ContributionAmendmentSerializer(serializers.ModelSerializer):
    proposed_by_phone = serializers.CharField(source='proposed_by.phone_number', read_only=True)
    proposed_by_name  = serializers.SerializerMethodField()
    approve_count     = serializers.IntegerField(read_only=True)
    reject_count      = serializers.IntegerField(read_only=True)
    votes             = ContributionAmendmentVoteSerializer(many=True, read_only=True)
    required_approvals = serializers.SerializerMethodField()
    changes_display   = serializers.SerializerMethodField()

    class Meta:
        model  = ContributionAmendment
        fields = [
            'id', 'contribution', 'proposed_by_phone', 'proposed_by_name',
            'changes', 'changes_display', 'reason', 'status',
            'approve_count', 'reject_count', 'required_approvals',
            'votes', 'created_at', 'resolved_at',
        ]
        read_only_fields = ['status', 'approve_count', 'reject_count', 'votes', 'resolved_at']

    def get_proposed_by_name(self, obj):
        return obj.proposed_by.name or obj.proposed_by.phone_number

    def get_required_approvals(self, obj):
        from .services import AmendmentService
        return AmendmentService._amendment_required(obj.contribution, obj.proposed_by)

    def get_changes_display(self, obj):
        """Human-readable summary of what will change."""
        LABELS = {
            'fixed_amount':     'Fixed amount per member',
            'target_amount':    'Target amount',
            'voting_threshold': 'Approval threshold',
            'end_date':         'End date',
            'period_months':    'Period (months)',
            'visibility':       'Visibility',
        }
        THRESHOLD_LABELS = {'admins': 'Admins only', '25': '25% of members', '50': '50% of members', '100': 'All members'}
        lines = []
        c = obj.contribution
        for field, new_val in obj.changes.items():
            label = LABELS.get(field, field)
            old_val = getattr(c, field, '—')
            if field in ('fixed_amount', 'target_amount') and old_val is not None:
                from decimal import Decimal as _D
                old_val = f"KES {_D(str(old_val)):,.0f}"
                new_val = f"KES {_D(str(new_val)):,.0f}"
            elif field == 'voting_threshold':
                old_val = THRESHOLD_LABELS.get(str(old_val), str(old_val))
                new_val = THRESHOLD_LABELS.get(str(new_val), str(new_val))
            lines.append({'field': label, 'from': str(old_val) if old_val is not None else 'None', 'to': str(new_val)})
        return lines


class ContributionJoinRequestSerializer(serializers.ModelSerializer):
    phone_number     = serializers.CharField(source='user.phone_number', read_only=True)
    name             = serializers.SerializerMethodField()
    invited_by_phone = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.user.name or None   # blank string → null

    class Meta:
        model  = ContributionJoinRequest
        fields = [
            'id', 'contribution', 'phone_number', 'name',
            'request_type', 'invited_by_phone',
            'status', 'created_at', 'reviewed_at',
        ]

    def get_invited_by_phone(self, obj):
        return obj.invited_by.phone_number if obj.invited_by else None
