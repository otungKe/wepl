from ._common import *  # shared imports + helpers (ADR-0013 split)


class ContributionService:

    @staticmethod
    @transaction.atomic
    def create_contribution(user, validated_data, member_phones=None, add_all_members=False):
        AccessPolicy.gate(user, "Verify your identity to create a contribution.")
        if validated_data.get('community'):
            from apps.communities.services import require_active_community
            require_active_community(validated_data['community'], 'create a contribution')
        # Governance quorum is enforced at request time against the real
        # contribution row (submit_disbursement_request / propose amendment),
        # which correctly accounts for members who join after creation. A
        # creation-time pre-check used to run here but was removed (issue #14):
        # it blocked legitimate solo/open contributions and crashed on
        # percentage thresholds (it queried participants via a fake proxy object).
        contribution = Contribution.objects.create(created_by=user, **validated_data)

        ContributionParticipant.objects.create(contribution=contribution, user=user, is_active=True)

        if add_all_members and contribution.community:
            from apps.communities.models import CommunityMembership
            members = CommunityMembership.objects.filter(
                community=contribution.community, is_active=True
            ).exclude(user=user).select_related('user')
            for m in members:
                ContributionParticipant.objects.get_or_create(
                    contribution=contribution, user=m.user,
                    defaults={'is_active': True},
                )
        elif member_phones:
            from apps.users.models import User
            for phone in member_phones:
                try:
                    member = User.objects.get(phone_number=phone)
                    if member != user:
                        ContributionParticipant.objects.get_or_create(
                            contribution=contribution, user=member,
                            defaults={'is_active': True},
                        )
                except User.DoesNotExist:
                    pass

        ActivityService.record(
            actor=user,
            verb='contribution_created',
            params={"contribution_title": contribution.title},
            visibility=Activity.Visibility.COMMUNITY,
            community=contribution.community,
        )
        return contribution

    @staticmethod
    def join_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        if contribution.status != 'active':
            raise ValidationError("This contribution is closed and no longer accepting new members.")

        # Section B: block joining a ROSCA mid-cycle.
        # Once the rotation has been initialised (slots exist), new members
        # cannot join the current cycle — they must wait for the next one.
        if contribution.contribution_type == 'ROSCA':
            from .models import ROSCASlot
            rotation_active = ROSCASlot.objects.filter(
                contribution=contribution, cycle_number=1
            ).exists()
            already_participant = ContributionParticipant.objects.filter(
                contribution=contribution, user=user
            ).exists()
            if rotation_active and not already_participant:
                raise ValidationError(
                    "This ROSCA rotation has already started. "
                    "New members can join after the current cycle completes."
                )
        participant, created = ContributionParticipant.objects.get_or_create(
            contribution=contribution, user=user
        )
        if not created:
            participant.is_active = True
            participant.save()

        if contribution.created_by != user:
            _notify(
                user=contribution.created_by,
                notification_type='contribution_joined',
                title=f"New participant in {contribution.title}",
                message=f"{_dn(user)} joined your contribution.",
                contribution_id=contribution.id,
            )
        return participant

    @staticmethod
    def leave_contribution(contribution_id, user):
        participant = ContributionParticipant.objects.filter(
            contribution_id=contribution_id, user=user
        ).first()
        if participant:
            participant.is_active = False
            participant.save()
        return participant

    @staticmethod
    def close_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can close this contribution.")
        contribution.status = 'closed'
        contribution.is_active = False
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def archive_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can archive this contribution.")
        contribution.status = 'archived'
        contribution.is_active = False
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def reopen_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can reopen this contribution.")
        contribution.status = 'active'
        contribution.is_active = True
        contribution.save(update_fields=['status', 'is_active'])
        return contribution

    @staticmethod
    def delete_contribution(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can delete this contribution.")
        if fund_balance('contribution', contribution.id) > 0:
            raise ValidationError(
                "Cannot delete a contribution with an active balance. "
                "Close it and disburse all funds before deleting."
            )
        contribution.delete()

    @staticmethod
    def get_participants(contribution_id):
        return ContributionParticipant.objects.filter(
            contribution_id=contribution_id, is_active=True
        ).select_related('user')

    @staticmethod
    def get_user_contributions(user, active_only=True):
        from django.db.models import Count, Q
        qs = Contribution.objects.filter(
            participants__user=user, participants__is_active=True
        ).distinct()
        if active_only:
            qs = qs.filter(is_active=True)
        return qs.annotate(
            active_participant_count=Count(
                'participants', filter=Q(participants__is_active=True), distinct=True
            )
        ).order_by('-created_at')

    @staticmethod
    def get_by_invite_code(invite_code):
        return Contribution.objects.filter(invite_code=invite_code).first()

    @staticmethod
    @transaction.atomic
    def contribute(user, contribution_id, amount, mpesa_receipt=None, idempotency_key=None):
        """
        Record an inbound member contribution.

        Writes to both the legacy mutable balance fields (for backwards compat)
        and the new immutable ledger (single source of truth going forward).
        Uses F() expressions for all balance updates — no read-modify-write.
        Idempotent when idempotency_key is supplied (e.g. M-Pesa receipt).
        """
        if amount <= 0:
            raise ValidationError("Amount must be greater than 0")

        # Tier-1 (KYC-approved) gate — centralized (ADR-0022).
        AccessPolicy.require_tier1(
            user, "Your identity verification must be approved before you can contribute.")

        contribution = Contribution.objects.select_for_update().get(id=contribution_id)

        if contribution.status != 'active':
            raise ValidationError("This contribution is closed and no longer accepting payments.")

        if not ContributionParticipant.objects.filter(
            contribution=contribution, user=user, is_active=True
        ).exists():
            raise ValidationError("User is not an active participant")

        # Section C — late contribution policy
        if contribution.end_date:
            from datetime import date, timedelta
            today = timezone.now().date()
            policy = contribution.late_contribution_policy

            if policy == 'strict' and today > contribution.end_date:
                raise ValidationError(
                    f"This contribution closed on "
                    f"{contribution.end_date.strftime('%d %b %Y')}. "
                    "No further payments are accepted."
                )
            elif policy == 'grace':
                grace_deadline = contribution.end_date + timedelta(
                    days=contribution.late_contribution_grace_days or 7
                )
                if today > grace_deadline:
                    raise ValidationError(
                        f"The grace period for this contribution ended on "
                        f"{grace_deadline.strftime('%d %b %Y')}. "
                        "No further payments are accepted."
                    )

        # ── Idempotency: don't double-credit the same M-Pesa receipt ──────────
        idem_key = idempotency_key or (
            f"contrib-{contribution_id}-{mpesa_receipt}" if mpesa_receipt
            else f"contrib-{contribution_id}-{user.id}-manual"
        )

        # ── Idempotency: if this journal was already posted, return its tx ─────
        if JournalEntry.objects.filter(idempotency_key=f"je-{idem_key}").exists():
            return ContributionTransaction.objects.filter(
                contribution=contribution, user=user,
                mpesa_receipt=mpesa_receipt,
            ).first()

        tx = ContributionTransaction.objects.create(
            contribution=contribution,
            user=user,
            amount=amount,
            transaction_type='CONTRIBUTION',
            mpesa_receipt=mpesa_receipt or None,
        )

        # ── FinancialTransaction (orchestration) ──────────────────────────────
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.CONTRIBUTION,
            amount=Decimal(str(amount)),
            initiated_by=user,
            contribution=contribution,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        tx.financial_transaction = ft
        tx.save(update_fields=['financial_transaction'])

        # ── Double-entry posting — the source of truth ────────────────────────
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.CONTRIBUTION,
            lines=_pm.contribution_lines(
                member=user, fund_type='contribution',
                fund_id=contribution.id, gross=Money(str(amount)),
            ),
            narration=f"Member contribution by {user.phone_number}",
            financial_transaction=ft,
            created_by=user,
        )

        # ── Side effects ──────────────────────────────────────────────────────
        # Amount is sensitive — keep the payer's own contribution private.
        ActivityService.record(
            actor=user,
            verb='contribution_payment',
            params={"amount": str(amount), "contribution_title": contribution.title},
            visibility=Activity.Visibility.PRIVATE,
        )

        pool_total = fund_balance('contribution', contribution.id)
        previous_amount = pool_total - Decimal(str(amount))

        if contribution.created_by != user:
            _notify(
                user=contribution.created_by,
                notification_type='contribution_payment',
                title=f"New contribution to {contribution.title}",
                message=f"{_dn(user)} contributed KES {amount:,.0f}.",
                contribution_id=contribution.id,
            )

        if contribution.target_amount and contribution.target_amount > 0:
            prev_pct = int((previous_amount / contribution.target_amount) * 100)
            curr_pct = int((pool_total / contribution.target_amount) * 100)
            for milestone in (50, 100):
                if prev_pct < milestone <= curr_pct:
                    label = "reached 50%!" if milestone == 50 else "is fully funded! 🎉"
                    for p in ContributionParticipant.objects.filter(
                        contribution=contribution, is_active=True
                    ):
                        _notify(
                            user=p.user,
                            notification_type='contribution_milestone',
                            title=f"{contribution.title} {label}",
                            message=(
                                f"Collected KES {pool_total} "
                                f"of KES {contribution.target_amount}."
                            ),
                            contribution_id=contribution.id,
                        )
                    break

        return tx


# ---------------------------------------------------------------------------
# ROSCA
# ---------------------------------------------------------------------------
