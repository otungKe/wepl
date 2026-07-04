from ._common import *  # shared imports + helpers (ADR-0013 split)


class AmendmentService:

    SENSITIVE_FIELDS = frozenset({
        'fixed_amount', 'target_amount', 'voting_threshold',
        'end_date', 'period_months', 'visibility',
    })
    DIRECT_FIELDS = frozenset({'title', 'description'})

    @staticmethod
    def _amendment_required(contribution, proposer):
        # Section C: use amendment_voting_threshold, not the disbursement threshold
        threshold = contribution.amendment_voting_threshold
        if threshold == 'admins':
            if contribution.community:
                from apps.communities.models import CommunityMembership
                participant_ids = set(
                    ContributionParticipant.objects.filter(
                        contribution=contribution, is_active=True,
                    ).values_list('user_id', flat=True)
                )
                eligible = CommunityMembership.objects.filter(
                    community=contribution.community,
                    user_id__in=participant_ids,
                    role__in=['admin', 'treasurer'],
                    is_active=True,
                ).exclude(user=proposer).count()
                if (contribution.created_by != proposer
                        and contribution.created_by_id in participant_ids):
                    creator_already = CommunityMembership.objects.filter(
                        community=contribution.community,
                        user=contribution.created_by,
                        role__in=['admin', 'treasurer'],
                        is_active=True,
                    ).exists()
                    if not creator_already:
                        eligible += 1
                return eligible
            else:
                is_participant = ContributionParticipant.objects.filter(
                    contribution=contribution,
                    user=contribution.created_by,
                    is_active=True,
                ).exists()
                if contribution.created_by != proposer and is_participant:
                    return 1
                return 0
        return contribution.required_approvals()

    @staticmethod
    def propose(contribution_id, user, changes: dict, reason: str = ''):
        AccessPolicy.gate(user, "Verify your identity to propose an amendment.")
        contribution = Contribution.objects.get(id=contribution_id)

        # Section C — check amendment_proposer setting
        proposer_policy = contribution.amendment_proposer
        if proposer_policy == 'creator':
            require(user, "contribution.lifecycle", contribution,
                    "Only the contribution creator can propose amendments.")
        elif proposer_policy == 'admins':
            require(user, "contribution.admin", contribution,
                    "Only admins and treasurers can propose amendments.")
        elif proposer_policy == 'members':
            require(user, "contribution.participate", contribution,
                    "Only active participants can propose amendments.")
        else:
            require(user, "contribution.admin", contribution,
                    "Only the contribution creator or a community admin can propose amendments.")

        # Quorum check: ensure at least one eligible voter exists for the amendment threshold.
        FinancialPermissions.assert_quorum_exists(
            contribution, contribution.amendment_voting_threshold, user,
            action="propose this amendment",
        )

        bad_keys = set(changes.keys()) - AmendmentService.SENSITIVE_FIELDS
        if bad_keys:
            raise ValidationError(
                f"Invalid fields for amendment: {bad_keys}. "
                "Only sensitive fields require a proposal."
            )
        if not changes:
            raise ValidationError("No changes provided.")

        if ContributionAmendment.objects.filter(
            contribution=contribution, status='PENDING'
        ).exists():
            raise ValidationError(
                "There is already a pending amendment for this contribution. "
                "Wait for it to be resolved before proposing another."
            )

        from decimal import Decimal, InvalidOperation
        if 'target_amount' in changes:
            try:
                ta = Decimal(str(changes['target_amount']))
                pool_bal = fund_balance('contribution', contribution.id)
                if ta < pool_bal:
                    raise ValidationError(
                        f"target_amount cannot be lower than the current balance "
                        f"of KES {pool_bal:,.0f}."
                    )
            except InvalidOperation:
                raise ValidationError("Invalid target_amount value.")
        if 'fixed_amount' in changes and contribution.amount_type != 'fixed':
            raise ValidationError(
                "fixed_amount can only be amended on fixed-amount contributions."
            )
        if 'end_date' in changes and contribution.tenure_type != 'date':
            raise ValidationError(
                "end_date can only be amended on contributions with a specific end date."
            )
        if 'period_months' in changes and contribution.tenure_type != 'period':
            raise ValidationError(
                "period_months can only be amended on period-based contributions."
            )

        serialised = {}
        for k, v in changes.items():
            try:
                serialised[k] = (
                    str(Decimal(str(v))) if k in ('fixed_amount', 'target_amount') else v
                )
            except Exception:
                serialised[k] = v

        amendment = ContributionAmendment.objects.create(
            contribution=contribution,
            proposed_by=user,
            changes=serialised,
            reason=reason,
        )

        required = AmendmentService._amendment_required(contribution, user)
        if required == 0:
            AmendmentService._apply(amendment, contribution)
            return ContributionAmendment.objects.get(id=amendment.id)

        for p in ContributionParticipant.objects.filter(
            contribution=contribution, is_active=True
        ).exclude(user=user).select_related('user'):
            _notify(
                user=p.user,
                notification_type='amendment_proposed',
                title=f"Amendment proposed — {contribution.title}",
                message=(
                    f"{user.phone_number} proposed changes to "
                    f"{', '.join(changes.keys())}. Vote now."
                ),
                contribution_id=contribution.id,
            )

        return amendment

    @staticmethod
    def get_amendments(contribution_id):
        return ContributionAmendment.objects.filter(
            contribution_id=contribution_id
        ).select_related('proposed_by', 'contribution').prefetch_related(
            'votes__voter'
        ).order_by('-created_at')

    @staticmethod
    @transaction.atomic
    def vote(amendment_id, voter, vote_choice: str):
        AccessPolicy.gate(voter, "Verify your identity to vote on an amendment.")
        amendment    = ContributionAmendment.objects.select_for_update().get(
            id=amendment_id, status='PENDING'
        )
        contribution = amendment.contribution

        if amendment.proposed_by == voter:
            raise PermissionDenied("You cannot vote on your own amendment proposal.")

        # Section C: amendment votes use amendment_voting_threshold (ADR-0009 policy)
        require(voter, "contribution.vote_amendment", contribution,
                "You are not authorised to vote on this amendment.")

        _, created = ContributionAmendmentVote.objects.get_or_create(
            amendment=amendment, voter=voter, defaults={'vote': vote_choice}
        )
        if not created:
            raise ValidationError("You have already voted on this amendment.")

        approvals  = amendment.votes.filter(vote='APPROVE').count()
        rejections = amendment.votes.filter(vote='REJECT').count()
        required   = AmendmentService._amendment_required(contribution, amendment.proposed_by)

        if approvals >= required:
            AmendmentService._apply(amendment, contribution)
            _notify(
                user=amendment.proposed_by,
                notification_type='amendment_approved',
                title=f"Amendment approved — {contribution.title}",
                message="Your proposed changes have been approved and applied.",
                contribution_id=contribution.id,
            )
        elif rejections >= required:
            amendment.status = 'REJECTED'
            amendment.resolved_at = timezone.now()
            amendment.save(update_fields=['status', 'resolved_at'])
            _notify(
                user=amendment.proposed_by,
                notification_type='amendment_rejected',
                title=f"Amendment rejected — {contribution.title}",
                message="Your proposed changes were not approved by the group.",
                contribution_id=contribution.id,
            )

        return ContributionAmendment.objects.get(id=amendment_id)

    @staticmethod
    def _apply(amendment, contribution):
        from decimal import Decimal
        from datetime import timedelta

        DECIMAL_FIELDS = {'fixed_amount', 'target_amount'}
        INT_FIELDS     = {'period_months'}

        update_fields = []
        for field, value in amendment.changes.items():
            if field in DECIMAL_FIELDS:
                setattr(contribution, field, Decimal(str(value)))
            elif field in INT_FIELDS:
                setattr(contribution, field, int(value))
            else:
                setattr(contribution, field, value)
            update_fields.append(field)

        # Governance cooldown (Issue 16): if the voting threshold was relaxed,
        # lock disbursement execution for 24 h so that pending approvals that
        # were cast under the old (stricter) rules cannot slip through the new
        # (looser) threshold and execute immediately.
        if 'voting_threshold' in amendment.changes:
            contribution.governance_locked_until = timezone.now() + timedelta(hours=24)
            if 'governance_locked_until' not in update_fields:
                update_fields.append('governance_locked_until')

        contribution.save(update_fields=update_fields)
        amendment.status      = 'APPROVED'
        amendment.resolved_at = timezone.now()
        amendment.save(update_fields=['status', 'resolved_at'])

    @staticmethod
    def withdraw(amendment_id, user):
        try:
            amendment = ContributionAmendment.objects.select_related('contribution').get(
                id=amendment_id
            )
        except ContributionAmendment.DoesNotExist:
            raise ValidationError("Amendment not found.")

        if amendment.proposed_by != user:
            raise PermissionDenied("Only the proposer can withdraw their amendment.")

        if amendment.status != 'PENDING':
            raise ValidationError(
                f"Cannot withdraw an amendment that is already {amendment.status.lower()}."
            )

        amendment.status      = 'WITHDRAWN'
        amendment.resolved_at = timezone.now()
        amendment.save(update_fields=['status', 'resolved_at'])
        return amendment


# ---------------------------------------------------------------------------
# Contribution Join Requests & Invitations
# ---------------------------------------------------------------------------
