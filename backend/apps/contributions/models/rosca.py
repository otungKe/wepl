"""ROSCA rotation — which participant receives in which cycle."""

from django.db import models

from .contribution import Contribution, ContributionParticipant


class ROSCASlot(models.Model):
    contribution = models.ForeignKey(Contribution, on_delete=models.CASCADE, related_name='rosca_slots')
    participant  = models.ForeignKey(ContributionParticipant, on_delete=models.CASCADE, related_name='rosca_slots')
    slot_order   = models.PositiveIntegerField()
    cycle_number = models.PositiveIntegerField(default=1)
    has_received = models.BooleanField(default=False)
    received_at  = models.DateTimeField(null=True, blank=True)
    payout_amount = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    class Meta:
        unique_together = ['contribution', 'slot_order', 'cycle_number']
        ordering = ['cycle_number', 'slot_order']

    def __str__(self):
        return (
            f"{self.contribution.title} | Cycle {self.cycle_number} "
            f"| Slot {self.slot_order} | {self.participant.user.phone_number}"
        )


# ---------------------------------------------------------------------------
# Standing Orders (scheduled automatic payouts)
# ---------------------------------------------------------------------------
