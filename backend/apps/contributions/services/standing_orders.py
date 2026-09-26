from ._common import *  # shared imports + helpers (ADR-0013 split)
from .contribution import _share_allocations


class StandingOrderService:

    @staticmethod
    @transaction.atomic
    def create_standing_order(user, contribution_id, data):
        AccessPolicy.gate(user, "Verify your identity to set up a standing order.")
        contribution = Contribution.objects.get(id=contribution_id)

        require(user, "contribution.admin", contribution,
                "Only the contribution creator or a community admin can create standing orders.")

        frequency = data.get('frequency', 'monthly')
        order = StandingOrder.objects.create(
            contribution=contribution,
            created_by=user,
            amount=data['amount'],
            frequency=frequency,
            payee_type=data.get('payee_type', 'fixed'),
            fixed_payee_phone=data.get('fixed_payee_phone') or None,
            next_run_at=timezone.now(),  # due immediately (admin can adjust)
        )

        if order.payee_type == 'rotating':
            participants = ContributionParticipant.objects.filter(
                contribution=contribution, is_active=True
            ).select_related('user').order_by('?')
            for i, p in enumerate(participants, start=1):
                StandingOrderSlot.objects.create(
                    order=order,
                    phone_number=p.user.phone_number,
                    name=p.user.name or '',
                    slot_order=i,
                )
        return order

    @staticmethod
    def get_standing_orders(contribution_id):
        return StandingOrder.objects.filter(
            contribution_id=contribution_id
        ).select_related('created_by').prefetch_related('slots')

    @staticmethod
    @transaction.atomic
    def execute_standing_order(order_id, user):
        """
        Execute a standing order — reserve pool funds and dispatch B2C via Celery.

        Key fixes vs. old code:
          - B2C HTTP call is OUTSIDE the atomic block (dispatched via on_commit → Celery).
          - next_run_at is advanced immediately after scheduling to prevent re-entry.
          - Pool balance is debited via F() (no read-modify-write).
        """
        order = StandingOrder.objects.select_for_update().get(id=order_id)

        require(user, "contribution.admin", order.contribution,
                "Only the creator or an admin can execute this order.")

        if not order.is_active:
            raise ValidationError("This standing order is no longer active.")

        contribution = Contribution.objects.select_for_update().get(
            id=order.contribution_id
        )
        if pool_cash(contribution.id) < order.amount:
            raise ValidationError("Insufficient funds in the contribution pool.")

        recipient_member = None
        if order.payee_type == 'fixed':
            recipient_phone = order.fixed_payee_phone
        else:
            next_slot = order.slots.select_for_update().filter(has_received=False).first()
            if not next_slot:
                raise ValidationError("All rotation slots have been paid out.")
            next_slot.has_received = True
            next_slot.received_at  = timezone.now()
            next_slot.save(update_fields=['has_received', 'received_at'])
            recipient_phone = next_slot.phone_number
            recipient_member = (ContributionParticipant.objects
                                .filter(contribution=contribution,
                                        user__phone_number=recipient_phone)
                                .select_related('user').first())

        # ── Reserve funds ─────────────────────────────────────────────────────
        now = timezone.now()
        # Idempotency key is anchored to the scheduled window (next_run_at),
        # not the wall-clock time of execution.  Two calls in the same scheduled
        # window produce the same key → safe against double-clicks and retries.
        # Falls back to minute-granularity wall-clock only if next_run_at is unset
        # (e.g. manually created orders before the scheduler ran).
        scheduled_window = order.next_run_at or now
        idem_key = f"so-{order.id}-{scheduled_window.strftime('%Y%m%d%H%M')}"
        ft, created = create_fin_transaction(
            idempotency_key=idem_key,
            op_type=FinancialTransaction.OpType.STANDING_ORDER,
            amount=order.amount,
            initiated_by=user,
            recipient_phone=recipient_phone,
            contribution=contribution,
            context_type='standing_order',
            context_id=order.id,
        )

        if not created and ft.state in (
            FinancialTransaction.State.SUCCESS,
            FinancialTransaction.State.PROCESSING,
        ):
            return order  # already in flight

        # Double-entry posting (P0-05). The pool is the group's (ADR-0027 §0.1),
        # so whoever runs the order is never charged for it. A rotating order
        # pays a member their turn, drawn from that member's share like a
        # ROSCA turn; a fixed payee (rent, a supplier) is a group expense,
        # split across the funded shares. A rotating slot whose phone no
        # longer matches a participant falls back to the group split.
        if recipient_member is not None:
            lines = _pm.disbursement_lines(
                member=recipient_member.user, fund_type='contribution',
                fund_id=contribution.id, amount=Money(str(order.amount)),
            )
        else:
            lines = _pm.pool_expense_lines(
                fund_type='contribution', fund_id=contribution.id,
                allocations=_share_allocations(contribution.id, order.amount),
            )
        post_journal(
            idempotency_key=f"je-{idem_key}",
            # A split is recorded as the group expense it is, so history does
            # not read each member's part as money paid to them.
            op_type=_pm.Op.STANDING_ORDER if recipient_member else _pm.Op.POOL_EXPENSE,
            lines=lines,
            narration=f"Standing order payout to {recipient_phone}",
            financial_transaction=ft,
            created_by=user,
        )


        # Advance schedule
        StandingOrder.objects.filter(pk=order.pk).update(
            last_executed_at=now,
            next_run_at=_compute_next_run(order.frequency, now),
        )

        ActivityService.record(
            actor=user,
            verb='standing_order_executed',
            params={"amount": str(order.amount), "recipient": recipient_phone},
            visibility=Activity.Visibility.PRIVATE,
        )

        # ── Dispatch B2C via Celery AFTER commit ──────────────────────────────
        ft_id = ft.id

        def _dispatch():
            from apps.payments.payouts import execute_payout
            from apps.core.dispatch import safe_enqueue
            safe_enqueue(execute_payout, ft_id, critical=True)

        transaction.on_commit(_dispatch)
        return order

    @staticmethod
    def cancel_standing_order(order_id, user):
        order = StandingOrder.objects.get(id=order_id)
        if order.created_by != user:
            raise PermissionDenied("Only the creator can cancel this order.")
        order.is_active = False
        order.save(update_fields=['is_active'])
        return order

    @staticmethod
    def update_standing_order(order_id, user, data):
        """Amend amount, frequency, or fixed_payee_phone on an active standing order."""
        order = StandingOrder.objects.get(id=order_id, is_active=True)
        if order.created_by != user:
            raise PermissionDenied("Only the creator can amend this standing order.")

        changed = False
        if 'amount' in data:
            amount = Decimal(str(data['amount']))
            if amount <= 0:
                raise ValidationError("Amount must be greater than zero.")
            order.amount = amount
            changed = True
        if 'frequency' in data:
            if data['frequency'] not in ('daily', 'weekly', 'monthly'):
                raise ValidationError("Invalid frequency.")
            order.frequency = data['frequency']
            changed = True
        if 'fixed_payee_phone' in data:
            if order.payee_type != 'fixed':
                raise ValidationError("Payee phone can only be changed on fixed-payee orders.")
            order.fixed_payee_phone = data['fixed_payee_phone'] or None
            changed = True

        if changed:
            order.save()
        return order


# ---------------------------------------------------------------------------
# Contribution Amendments
# ---------------------------------------------------------------------------
