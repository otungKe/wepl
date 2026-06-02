from rest_framework import serializers

from .models import Community, CommunityJoinRequest, CommunityMembership


class CommunitySerializer(serializers.ModelSerializer):

    created_by          = serializers.CharField(source="created_by.phone_number", read_only=True)
    created_by_name     = serializers.SerializerMethodField()
    member_count        = serializers.SerializerMethodField()
    is_member           = serializers.SerializerMethodField()
    join_request_status = serializers.SerializerMethodField()
    invite_code         = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            "id", "name", "description", "community_photo", "is_private",
            "invite_code", "has_welfare_fund", "has_shares_fund", "category",
            "location", "created_by", "created_by_name", "member_count",
            "is_member", "join_request_status", "created_at",
            # Section A governance settings
            "join_policy", "invite_permission", "contribution_permission",
            "member_list_visibility", "max_members",
            # Section B cooling-off period
            "cooling_off_days",
        ]

    # ── Internal helpers ───────────────────────────────────────────────────────

    def _request_user(self):
        request = self.context.get("request")
        return request.user if request else None

    def _is_active_member(self, obj) -> bool:
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return False
        return obj.memberships.filter(user=user, is_active=True).exists()

    # ── Field methods ──────────────────────────────────────────────────────────

    def get_created_by_name(self, obj):
        return obj.created_by.name or obj.created_by.phone_number

    def get_member_count(self, obj):
        # Use annotated value when available (avoids extra query from DiscoverView)
        if hasattr(obj, "annotated_member_count"):
            return obj.annotated_member_count
        return obj.memberships.filter(is_active=True).count()

    def get_is_member(self, obj):
        return self._is_active_member(obj)

    def get_join_request_status(self, obj):
        """Returns 'PENDING' | 'APPROVED' | 'REJECTED' | None."""
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return None
        req = obj.join_requests.filter(requester=user).order_by("-created_at").first()
        return req.status if req else None

    def get_invite_code(self, obj):
        """
        Only expose the invite code to active members.
        Leaking it on the public discover feed defeats the purpose of private groups.
        """
        return obj.invite_code if self._is_active_member(obj) else None


class CommunityWriteSerializer(serializers.ModelSerializer):
    """Used for create / partial-update — strips read-only/derived fields
    and the invite_code so clients cannot set it directly."""

    class Meta:
        model  = Community
        fields = [
            "name", "description", "community_photo", "is_private",
            "has_welfare_fund", "has_shares_fund", "category", "location",
            # Section A governance settings (writable on create/update)
            "join_policy", "invite_permission", "contribution_permission",
            "member_list_visibility", "max_members",
            # Section B
            "cooling_off_days",
        ]

    def validate_name(self, value):
        value = (value or "").strip()
        if len(value) < 3:
            raise serializers.ValidationError("Community name must be at least 3 characters.")
        return value


class CommunityMembershipSerializer(serializers.ModelSerializer):
    """
    Serializer for community members.

    Privacy rules applied:
      phone_visibility='nobody'   → phone masked
      show_online_status=False    → is_online always None (hidden)
      show_online_status=True     → is_online reflects last_seen within 5 min

    joined_at is intentionally excluded — it's internal information.
    """
    from datetime import timedelta
    _ONLINE_THRESHOLD = timedelta(minutes=5)

    phone_number  = serializers.SerializerMethodField()
    name          = serializers.SerializerMethodField()
    profile_photo = serializers.ImageField(source="user.profile_photo", read_only=True)
    is_online     = serializers.SerializerMethodField()

    class Meta:
        model  = CommunityMembership
        fields = ["id", "phone_number", "name", "profile_photo", "role", "is_active", "is_online"]

    def get_phone_number(self, obj):
        try:
            vis = obj.user.privacy_prefs.phone_visibility
        except Exception:
            vis = "members"

        if vis == "nobody":
            return None
        return obj.user.phone_number

    def get_name(self, obj):
        return obj.user.name or obj.user.phone_number

    def get_is_online(self, obj):
        """Return True/False if user has show_online_status=True, else None."""
        try:
            if not obj.user.privacy_prefs.show_online_status:
                return None   # user has opted out — don't reveal
        except Exception:
            pass  # no prefs row → default show_online_status=True

        if not obj.user.last_seen:
            return False

        from django.utils import timezone
        from datetime import timedelta
        return (timezone.now() - obj.user.last_seen) <= timedelta(minutes=5)


class CommunityJoinRequestSerializer(serializers.ModelSerializer):
    requester_phone = serializers.CharField(source="requester.phone_number", read_only=True)
    requester_name  = serializers.SerializerMethodField()
    community_name  = serializers.CharField(source="community.name", read_only=True)

    class Meta:
        model  = CommunityJoinRequest
        fields = [
            "id", "community", "community_name",
            "requester_phone", "requester_name",
            "status", "created_at",
        ]

    def get_requester_name(self, obj):
        return obj.requester.name or obj.requester.phone_number
