"""Share funds and member holdings (the shares sub-ledger's domain side)."""

from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils.functional import cached_property

from apps.communities.models import Community


class SharesFund(models.Model):
    # Program spine (ADR-0026): this fund is the archetype profile of a Program.
    # Stamped at creation, backfilled for pre-spine rows (hence nullable).
    program = models.OneToOneField(
        'organizations.Program', null=True, blank=True,
        on_delete=models.PROTECT, related_name='shares_profile',
    )

    community = models.OneToOneField(
        'communities.Community', on_delete=models.PROTECT, related_name='shares_fund',
        null=True, blank=True,
    )
    name        = models.CharField(max_length=255, default='Shares Fund')
    share_price = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal('100.00'))
    created_at  = models.DateTimeField(auto_now_add=True)

    @cached_property
    def pool_balance(self):
        """The fund's ledger-derived pool, read once per instance.

        Every holding's ``ownership_pct`` needs the same denominator, so hanging
        it on the fund means one read for a whole fund rather than one per
        holder — provided the holdings share this instance.
        """
        from apps.ledger.balances import fund_balance
        return fund_balance('shares', self.id)

    def __str__(self):
        return f"{self.community.name if self.community else '?'} — {self.name}"



class ShareHolding(models.Model):
    """A member's membership of a shares fund. The *amounts* are not stored.

    ``shares_count`` and ``total_contributed`` were mutable counters incremented
    alongside each purchase — exactly the kind of balance column ADR-0002 removed
    from the rest of the money path, and they drifted for the usual reason (a
    write separate from the journal). They are now derived from the member's
    shares sub-ledger, which is the source of truth and was never wrong.

    This row remains because membership of a fund is a fact of its own: a member
    can be enrolled with nothing bought yet, and the fund lists its holders.
    """
    shares_fund = models.ForeignKey(SharesFund, on_delete=models.CASCADE, related_name='holdings')
    user        = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)

    class Meta:
        unique_together = ['shares_fund', 'user']

    @cached_property
    def total_contributed(self):
        """Money this member has put into the fund, from their sub-ledger.

        Cached per instance: ``shares_count`` and ``ownership_pct`` are both
        expressed in terms of it, and serializing a fund walks every holder. A
        long-lived instance that spans a purchase should be re-fetched rather
        than read again.
        """
        from apps.ledger.balances import member_fund_balance
        return member_fund_balance(self.user, 'shares', self.shares_fund_id)

    @property
    def shares_count(self):
        """Shares held = the member's sub-ledger balance over the share price.

        ``share_price`` is fixed at fund creation and has no write path, so this
        is the same figure the old counter accumulated purchase by purchase.
        """
        price = self.shares_fund.share_price
        if not price:
            return Decimal('0')
        return (self.total_contributed / price).quantize(Decimal('0.0001'))

    @property
    def ownership_pct(self):
        pool = self.shares_fund.pool_balance
        if not pool:
            return Decimal('0')
        return (self.total_contributed / pool * 100).quantize(Decimal('0.01'))

    def __str__(self):
        return f"{self.user.phone_number} | {self.shares_count} shares"


# ---------------------------------------------------------------------------
# ROSCA (Rotating Savings)
# ---------------------------------------------------------------------------
