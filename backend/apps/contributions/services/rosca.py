from ._common import *  # shared imports + helpers (ADR-0013)


class ROSCAService:

    @staticmethod
    def initialize_rotation(contribution_id, user):
        contribution = Contribution.objects.get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can initialize the rotation.")

        participants = list(ContributionParticipant.objects.filter(
            contribution=contribution, is_active=True
        ))
        if len(participants) < 2:
            raise ValidationError("At least 2 participants required.")

        ROSCASlot.objects.filter(contribution=contribution, cycle_number=1).delete()
        random.shuffle(participants)
        slots = [
            ROSCASlot(contribution=contribution, participant=p, slot_order=i + 1, cycle_number=1)
            for i, p in enumerate(participants)
        ]
        ROSCASlot.objects.bulk_create(slots)

        for slot in ROSCASlot.objects.filter(
            contribution=contribution, cycle_number=1
        ).order_by('slot_order'):
            _notify(
                user=slot.participant.user,
                notification_type='rosca_rotation_set',
                title=f"Rotation set for {contribution.title}",
                message=(
                    f"You are slot #{slot.slot_order}. "
                    f"Contribute KES {contribution.fixed_amount or contribution.cycle_amount} each cycle."
                ),
                contribution_id=contribution.id,
            )

        return ROSCASlot.objects.filter(
            contribution=contribution, cycle_number=1
        ).select_related('participant__user').order_by('slot_order')

    @staticmethod
    def get_rotation_status(contribution_id):
        return ROSCASlot.objects.filter(
            contribution_id=contribution_id
        ).select_related('participant__user').order_by('cycle_number', 'slot_order')

    @staticmethod
    @transaction.atomic
    def mark_slot_paid(contribution_id, user):
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)
        require(user, "contribution.lifecycle", contribution,
                "Only the creator can advance the rotation.")

        current_slot = ROSCASlot.objects.filter(
            contribution=contribution, has_received=False
        ).order_by('cycle_number', 'slot_order').first()

        if not current_slot:
            raise ValidationError("All slots have been paid out for this cycle.")

        payout_amount = fund_balance('contribution', contribution.id)

        current_slot.has_received  = True
        current_slot.received_at   = timezone.now()
        current_slot.payout_amount = payout_amount
        current_slot.save()

        # Legacy transaction record
        tx = ContributionTransaction.objects.create(
            contribution=contribution,
            user=current_slot.participant.user,
            amount=payout_amount,
            transaction_type='WITHDRAWAL',
            note=f"ROSCA payout — cycle {current_slot.cycle_number}, slot {current_slot.slot_order}",
        )

        idem_key = f"rosca-payout-{contribution.id}-cycle{current_slot.cycle_number}-slot{current_slot.slot_order}"
        ft, _ = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.ROSCA_PAYOUT,
            amount=payout_amount,
            initiated_by=user,
            recipient_phone=current_slot.participant.user.phone_number,
            contribution=contribution,
            context_type='rosca_slot',
            context_id=current_slot.id,
            initial_state=FinancialTransaction.State.SUCCESS,
        )
        tx.financial_transaction = ft
        tx.save(update_fields=['financial_transaction'])
        # Double-entry posting: payout draws the recipient's pool share.
        post_journal(
            idempotency_key=f"je-{idem_key}",
            op_type=_pm.Op.ROSCA_PAYOUT,
            lines=_pm.disbursement_lines(
                member=current_slot.participant.user, fund_type='contribution',
                fund_id=contribution.id, amount=Money(str(payout_amount)),
            ),
            narration=f"ROSCA payout — cycle {current_slot.cycle_number}, slot {current_slot.slot_order}",
            financial_transaction=ft,
            created_by=user,
        )

        _notify(
            user=current_slot.participant.user,
            notification_type='rosca_payout',
            title="It's your ROSCA turn!",
            message=(
                f"KES {payout_amount:,.0f} designated for your payout "
                f"from '{contribution.title}'."
            ),
            contribution_id=contribution.id,
        )
        return current_slot


# ---------------------------------------------------------------------------
# Multi-signature Disbursement
# ---------------------------------------------------------------------------
