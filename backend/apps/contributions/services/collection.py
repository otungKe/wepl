"""A collection for a named member (ADR-0027 §0.2).

Welfare for a small group is a one-off collection, not a standing fund: members
chip in for one person (a hospital bill, a funeral) and the whole of it goes to
them. Every pay-in is attributed to the beneficiary whoever paid it
(``posting_map.attributed_contribution_lines``), so the collection only ever
holds the beneficiary's money, and one admin hands it over, closing it. The
beneficiary cannot hand it over to themselves.

Because the money is the beneficiary's from the moment it lands, the pool
paths that spend or lend a group's money (voted payouts, pool actions, exits,
advances, pool income) are closed on a collection: the hand-over is its only
way out.
"""
from ._common import *  # shared imports + helpers (ADR-0013 split)


def is_collection(contribution) -> bool:
    return contribution.contribution_type == Contribution.TYPE_COLLECTION


def refuse_on_collection(contribution, what: str) -> None:
    if is_collection(contribution):
        raise ValidationError(
            f"A collection is handed over to the member it is for; you can't {what} from it.")


class CollectionService:

    @staticmethod
    def check_new(user, validated_data) -> None:
        """Validate a collection before it is created: it names a beneficiary
        who is an active member of the collection's community."""
        from apps.communities.models import CommunityMembership
        beneficiary = validated_data.get('beneficiary')
        community = validated_data.get('community')
        if beneficiary is None:
            raise ValidationError("Name the member this collection is for.")
        if community is None:
            raise ValidationError("A collection belongs to a community.")
        if not CommunityMembership.objects.filter(
                community=community, user=beneficiary, is_active=True).exists():
            raise ValidationError("The member this collection is for must be in the community.")

    @staticmethod
    @transaction.atomic
    def hand_over(user, contribution_id):
        """Pay everything collected so far to the beneficiary and close the
        collection. A failed payout restores the money (the settlement target
        reverses it), and a fresh hand-over sends it again."""
        from .disbursement import DisbursementService
        contribution = Contribution.objects.select_for_update().get(id=contribution_id)
        if not is_collection(contribution):
            raise ValidationError("Only a collection is handed over.")
        require(user, "community.finance.manage", contribution.community,
                "Only community admins can hand over a collection.")
        beneficiary = contribution.beneficiary
        if user.id == beneficiary.id:
            raise PermissionDenied(
                "Another admin must hand over a collection that is for you.")
        amount = member_fund_balance(beneficiary, 'contribution', contribution.id)
        if amount <= 0:
            raise ValidationError("There is nothing collected to hand over.")

        req = DisbursementRequest.objects.create(
            contribution=contribution, requested_by=beneficiary, amount=amount,
            reason=f"Collection handed over: {contribution.title}"[:255],
            recipient_phone=beneficiary.phone_number,
            kind=DisbursementRequest.KIND_HANDOVER,
        )
        req.transition_to('APPROVED')
        DisbursementService._pay_out_share(req, contribution)

        if contribution.status == 'active':
            contribution.status = 'closed'
            contribution.save(update_fields=['status'])
        AuditService.log(
            "contribution.collection_handed_over", actor=user, target=req,
            tenant=getattr(contribution.community, "tenant_id", None),
            metadata={"amount": str(req.amount), "contribution_id": contribution.id,
                      "beneficiary_id": beneficiary.id},
        )
        return req
