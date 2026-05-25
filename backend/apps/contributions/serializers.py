from rest_framework import serializers

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
    created_by      = serializers.CharField(source='created_by.phone_number', read_only=True)
    participant_count = serializers.SerializerMethodField()
    user_balance    = serializers.SerializerMethodField()
    voting_label    = serializers.SerializerMethodField()

    class Meta:
        model = Contribution
        fields = [
            'id', 'title', 'description', 'visibility',
            'created_by', 'community', 'invite_code',
            'target_amount', 'current_amount',
            'tenure_type', 'end_date', 'period_months',
            'frequency', 'amount_type', 'fixed_amount',
            'voting_threshold', 'voting_label',
            'min_approvals', 'is_active', 'status', 'is_campaign',
            'participant_count', 'user_balance', 'created_at',
        ]
        extra_kwargs = {
            'invite_code':    {'read_only': True},
            'current_amount': {'read_only': True},
        }

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
        # Use prefetch if present (injected by list views via Prefetch(..., to_attr=))
        prefetched = getattr(obj, '_user_balance_list', None)
        if prefetched is not None:
            return str(prefetched[0].amount) if prefetched else '0.00'
        balance = obj.balances.filter(user=request.user).first()
        return str(balance.amount) if balance else '0.00'

    def get_voting_label(self, obj):
        labels = {
            'admins': 'Admins only',
            '25': '25% of members',
            '50': '50% of members',
            '100': 'All members',
        }
        return labels.get(obj.voting_threshold, obj.voting_threshold)

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
    phone_number = serializers.CharField(source='user.phone_number', read_only=True)
    name         = serializers.SerializerMethodField()

    def get_name(self, obj):
        return obj.user.name or None   # blank string → null so frontend || fallback works cleanly

    class Meta:
        model = ContributionParticipant
        fields = ['id', 'phone_number', 'name', 'joined_at', 'is_active']


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

    class Meta:
        model = SharesFund
        fields = ['id', 'community', 'name', 'share_price', 'total_pool', 'total_shares', 'holdings', 'created_at']

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

    class Meta:
        model = DisbursementRequest
        fields = [
            'id', 'contribution', 'requested_by_phone', 'amount', 'reason',
            'recipient_phone', 'status', 'approve_count', 'reject_count',
            'required_approvals', 'votes', 'created_at', 'executed_at',
        ]
        read_only_fields = ['status', 'approve_count', 'reject_count', 'required_approvals', 'votes', 'executed_at']

    def get_required_approvals(self, obj):
        return obj.contribution.required_approvals()


# ---------------------------------------------------------------------------
# Welfare
# ---------------------------------------------------------------------------

class WelfareFundSerializer(serializers.ModelSerializer):
    class Meta:
        model = WelfareFund
        fields = ['id', 'community', 'name', 'balance', 'monthly_contribution', 'created_at']
        read_only_fields = ['balance']


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
