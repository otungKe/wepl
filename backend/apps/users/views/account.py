from ._common import *  # shared imports/helpers (ADR-0013)


class AccountDeletionView(APIView):
    """
    DELETE /api/users/account/

    Kenya Data Protection Act 2019, Section 26: right to erasure of personal data.
    Financial audit trails (ledger, transactions) are retained as required by CBK.
    PII is anonymised rather than hard-deleted.

    Blocks if:
      - User has unresolved advances (PENDING / APPROVED / DISBURSED)
      - User is the creator of a community that still has active members

    Process:
      1. Pre-condition checks
      2. Anonymise KYC: clear PII fields, delete ID scan files from storage
      3. Delete profile photo from storage
      4. Blacklist all outstanding JWT refresh tokens
      5. Anonymise User record: clear PII, disable account, invalidate credentials
    """
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user

        # ── Pre-condition: no outstanding advances ────────────────────────────
        from apps.contributions.models import EmergencyAdvance
        active_advances = EmergencyAdvance.objects.filter(
            borrower=user,
            status__in=['PENDING', 'APPROVED', 'DISBURSED'],
        )
        if active_advances.exists():
            return Response(
                {
                    'error': (
                        'You have outstanding advance(s) that must be repaid '
                        'before your account can be deleted.'
                    )
                },
                status=status.HTTP_409_CONFLICT,
            )

        # ── Pre-condition: not sole creator of a community with active members ─
        from apps.communities.models import Community, CommunityMembership
        for community in Community.objects.filter(created_by=user):
            others = CommunityMembership.objects.filter(
                community=community, is_active=True
            ).exclude(user=user).count()
            if others > 0:
                return Response(
                    {
                        'error': (
                            f"You are the creator of '{community.name}' which has "
                            f"{others} active member(s). Transfer ownership or "
                            "ask all members to leave before deleting your account."
                        )
                    },
                    status=status.HTTP_409_CONFLICT,
                )

        # ── Anonymise KYC profile ─────────────────────────────────────────────
        try:
            kyc = user.kyc
            for field_name in ('id_front', 'id_back'):
                file_field = getattr(kyc, field_name)
                if file_field:
                    try:
                        file_field.delete(save=False)
                    except Exception:
                        pass
            kyc.given_names    = '[deleted]'
            kyc.surname        = '[deleted]'
            kyc.id_number      = f'DELETED-{user.id}'
            kyc.email          = ''
            kyc.county         = 'Nairobi'
            kyc.occupation     = '[deleted]'
            kyc.rejection_reason = ''
            kyc.save()
        except Exception:
            pass  # no KYC profile — fine

        # ── Delete profile photo ───────────────────────────────────────────────
        if user.profile_photo:
            try:
                user.profile_photo.delete(save=False)
            except Exception:
                pass

        # ── Blacklist all outstanding JWT tokens ──────────────────────────────
        try:
            from rest_framework_simplejwt.token_blacklist.models import OutstandingToken
            from rest_framework_simplejwt.tokens import RefreshToken as RT
            for token in OutstandingToken.objects.filter(user=user):
                try:
                    RT(token.token).blacklist()
                except Exception:
                    pass
        except Exception:
            pass

        # ── Anonymise user record (PII scrub) ─────────────────────────────────
        user.phone_number      = f'+0000{user.id:08d}'
        user.name              = '[deleted]'
        user.bio               = ''
        user.pin               = ''
        user.is_pin_set        = False
        user.is_active         = False
        user.is_phone_verified = False
        user.profile_photo     = None
        user.save()

        logger.info("Account deletion: user %d anonymised successfully.", user.id)
        return Response(status=status.HTTP_204_NO_CONTENT)
