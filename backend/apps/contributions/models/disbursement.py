"""Requests to pay money out of a pool, and the votes on them."""

from django.conf import settings
from django.db import models

from apps.core.exceptions import TransitionError

from .contribution import Contribution


class DisbursementRequest(models.Model):
    """
    State machine:
        PENDING  → APPROVED  → EXECUTED   (success: vote approved → funds dispatched)
                 ↘ REJECTED               (terminal — vote rejected)
                 ↘ CANCELLED              (terminal — requester withdrew before vote)
        EXECUTED → APPROVED               (B2C failure rollback — admin can re-trigger)

    All status changes must go through transition_to() — direct .status assignment
    on a saved instance will raise TransitionError from save().
    """

    STATUS_CHOICES = (
        ('PENDING',   'Pending'),
        ('APPROVED',  'Approved'),
        ('REJECTED',  'Rejected'),
        ('EXECUTED',  'Executed'),
        ('CANCELLED', 'Cancelled'),
    )

    # A payout is money the group spends, split across shares (ADR-0027 §0.1).
    # An exit is a leaving member asking for their own share back (§0.4): the
    # group votes it like any payout, and must decide it by ``decide_by``.
    # A wind-up pays every member out through one of these per member, created
    # already approved by the group's wind-up vote (services/wind_up.py).
    KIND_PAYOUT = 'payout'
    KIND_EXIT = 'exit'
    KIND_WINDUP = 'windup'
    KIND_CHOICES = (
        (KIND_PAYOUT, 'Payout'),
        (KIND_EXIT,   'Exit settlement'),
        (KIND_WINDUP, 'Wind-up payout'),
    )
    EXIT_DECISION_DAYS = 30

    VALID_TRANSITIONS = {
        'PENDING':   frozenset({'APPROVED', 'REJECTED', 'CANCELLED'}),
        'APPROVED':  frozenset({'EXECUTED'}),
        'EXECUTED':  frozenset({'APPROVED'}),   # B2C failure rollback only
        'REJECTED':  frozenset(),                # terminal
        'CANCELLED': frozenset(),                # terminal
    }

    contribution   = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='disbursement_requests')
    requested_by   = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disbursement_requests')
    amount         = models.DecimalField(max_digits=12, decimal_places=2)
    reason         = models.TextField()
    recipient_phone = models.CharField(max_length=20)
    status         = models.CharField(max_length=20, choices=STATUS_CHOICES, default='PENDING')
    kind           = models.CharField(
        max_length=10, choices=KIND_CHOICES, default=KIND_PAYOUT,
        # db_default so the instance still serving during a deploy, which
        # does not know this column, can keep inserting payout requests.
        db_default=KIND_PAYOUT)
    decide_by      = models.DateTimeField(null=True, blank=True)
    created_at     = models.DateTimeField(auto_now_add=True)
    executed_at    = models.DateTimeField(null=True, blank=True)

    @property
    def approve_count(self):
        return self.votes.filter(vote='APPROVE').count()

    @property
    def reject_count(self):
        return self.votes.filter(vote='REJECT').count()

    class Meta:
        indexes = [
            models.Index(fields=['contribution', '-created_at'], name='disburse_req_contrib_date_idx'),
        ]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._committed_status: str = self.status
        self._in_transition: bool = False

    def save(self, *args, **kwargs):
        """Block direct .status = '...' assignments — use transition_to() instead."""
        if (
            self.pk
            and self.status != self._committed_status
            and not self._in_transition
        ):
            raise TransitionError(
                f"DisbursementRequest {self.pk}: direct status assignment is not allowed "
                f"({self._committed_status!r} → {self.status!r}). "
                "Use transition_to() instead."
            )
        super().save(*args, **kwargs)
        self._committed_status = self.status

    def transition_to(self, new_status: str, *, executed_at=None) -> None:
        """
        Atomically advance the request's status.

        Uses UPDATE WHERE status = <current> so concurrent voters
        cannot both successfully transition the same request.
        Raises TransitionError on invalid graph edge or concurrent conflict.
        """
        if new_status not in self.VALID_TRANSITIONS.get(self.status, frozenset()):
            raise TransitionError(
                f"DisbursementRequest {self.id}: invalid transition "
                f"{self.status!r} → {new_status!r}. "
                f"Allowed from {self.status!r}: "
                f"{sorted(self.VALID_TRANSITIONS.get(self.status, set()))}"
            )

        update_kwargs: dict = {'status': new_status}
        if executed_at is not None:
            update_kwargs['executed_at'] = executed_at

        rows = DisbursementRequest.objects.filter(
            pk=self.pk, status=self.status,
        ).update(**update_kwargs)

        if rows == 0:
            raise TransitionError(
                f"DisbursementRequest {self.id}: transition {self.status!r} → {new_status!r} "
                "lost concurrent race — another process already advanced this request."
            )

        self._in_transition = True
        self.status = new_status
        self._committed_status = new_status
        self._in_transition = False
        if executed_at is not None:
            self.executed_at = executed_at

    def __str__(self):
        return f"{self.contribution.title} | KES {self.amount} | {self.status}"



class DisbursementVote(models.Model):
    VOTE_CHOICES = (('APPROVE', 'Approve'), ('REJECT', 'Reject'))
    request  = models.ForeignKey(DisbursementRequest, on_delete=models.CASCADE, related_name='votes')
    voter    = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disbursement_votes')
    vote     = models.CharField(max_length=10, choices=VOTE_CHOICES)
    voted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['request', 'voter']

    def __str__(self):
        return f"{self.voter.phone_number} | {self.vote} | {self.request}"


# ---------------------------------------------------------------------------
# Welfare Fund (optional, per contribution group or community)
# ---------------------------------------------------------------------------
