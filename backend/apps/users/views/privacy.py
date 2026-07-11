from ._common import *  # shared imports/helpers (ADR-0013)


class PrivacyPreferencesView(APIView):
    """
    GET   /api/users/privacy/  — return the user's current privacy settings
    PATCH /api/users/privacy/  — update one or more privacy settings

    Fields: phone_visibility, photo_visibility, contribution_visibility
            (each: 'everyone' | 'members' | 'nobody')
            discoverable (bool), show_online_status (bool)
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
        return Response({f: getattr(prefs, f) for f in PRIVACY_FIELDS})

    def patch(self, request):
        from django.core.exceptions import ValidationError as DjangoValidationError

        prefs, _ = PrivacyPreferences.objects.get_or_create(user=request.user)
        visibility_values = {'everyone', 'members', 'nobody'}
        bool_fields       = {'discoverable', 'show_online_status'}
        vis_fields        = {'phone_visibility', 'photo_visibility', 'contribution_visibility'}
        changed = False

        for field in PRIVACY_FIELDS:
            if field not in request.data:
                continue
            val = request.data[field]
            if field in bool_fields:
                if not isinstance(val, bool):
                    return Response(
                        {'error': f"'{field}' must be true or false."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            elif field in vis_fields:
                if val not in visibility_values:
                    return Response(
                        {'error': f"'{field}' must be one of: {sorted(visibility_values)}."},
                        status=status.HTTP_400_BAD_REQUEST,
                    )
            setattr(prefs, field, val)
            changed = True

        if changed:
            prefs.save()

        return Response({f: getattr(prefs, f) for f in PRIVACY_FIELDS})


# ─── Account Deletion ────────────────────────────────────────────────────────
