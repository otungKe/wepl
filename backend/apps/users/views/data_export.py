from ._common import *  # shared imports/helpers (ADR-0013 view split)


class DataExportView(APIView):
    """GET /api/users/data-export/ — compile everything WEPL holds about the
    requesting user into one JSON document (self-serve data-rights export).

    Scoped strictly to request.user; assembled read-only from the user's own
    records. Financial records are included as the user's own history."""
    permission_classes = [IsActiveSession]

    def get(self, request):
        from django.utils import timezone
        u = request.user

        # Profile & account
        profile = {
            "phone_number": u.phone_number,
            "name": getattr(u, "name", ""),
            "bio": getattr(u, "bio", ""),
            "is_phone_verified": u.is_phone_verified,
            "date_joined": u.date_joined.isoformat() if getattr(u, "date_joined", None) else None,
        }

        # KYC
        kyc = None
        try:
            k = u.kyc
            kyc = {
                "status": k.status,
                "given_names": k.given_names,
                "surname": k.surname,
                "county": getattr(k, "county", ""),
                "physical_address": getattr(k, "physical_address", ""),
                "email_verified": k.email_verified,
                "submitted_at": k.created_at.isoformat() if getattr(k, "created_at", None) else None,
            }
        except Exception:
            kyc = {"status": "not_submitted"}

        # Preferences
        privacy = None
        try:
            p = u.privacy_prefs
            privacy = {f: getattr(p, f) for f in (
                "phone_visibility", "photo_visibility", "contribution_visibility",
                "discoverable", "show_online_status")}
        except Exception:
            privacy = None

        # Communities
        from apps.communities.models import CommunityMembership
        communities = [
            {"name": m.community.name, "role": m.role,
             "joined_at": m.joined_at.isoformat(), "is_active": m.is_active}
            for m in CommunityMembership.objects.filter(user=u).select_related("community")
        ]

        # Contributions the user participates in
        from apps.contributions.models import ContributionParticipant, ContributionTransaction
        contributions = [
            {"title": pt.contribution.title, "type": pt.contribution.contribution_type,
             "is_active": pt.is_active}
            for pt in ContributionParticipant.objects.filter(user=u).select_related("contribution")
        ]

        # The user's own contribution transactions
        transactions = [
            {"contribution": t.contribution.title, "amount": str(t.amount),
             "type": t.transaction_type, "mpesa_receipt": t.mpesa_receipt,
             "date": t.created_at.isoformat()}
            for t in ContributionTransaction.objects.filter(user=u)
                .select_related("contribution").order_by("-created_at")[:500]
        ]

        # Payment methods
        payment_methods = [
            {"kind": pm.kind, "display": pm.display, "is_default": pm.is_default}
            for pm in u.payment_methods.all()
        ]

        return Response({
            "exported_at": timezone.now().isoformat(),
            "account": profile,
            "identity_verification": kyc,
            "privacy_preferences": privacy,
            "communities": communities,
            "contributions": contributions,
            "transactions": transactions,
            "payment_methods": payment_methods,
        })
