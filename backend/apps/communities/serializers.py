from rest_framework import serializers

from .models import Community, CommunityMembership, CommunityJoinRequest


class CommunitySerializer(serializers.ModelSerializer):

    created_by = serializers.CharField(
        source='created_by.phone_number',
        read_only=True
    )
    created_by_name     = serializers.SerializerMethodField()
    member_count        = serializers.SerializerMethodField()
    is_member           = serializers.SerializerMethodField()
    join_request_status = serializers.SerializerMethodField()

    class Meta:
        model = Community
        fields = [
            'id',
            'name',
            'description',
            'community_photo',
            'is_private',
            'invite_code',
            'has_welfare_fund',
            'has_shares_fund',
            'category',
            'location',
            'created_by',
            'created_by_name',
            'member_count',
            'is_member',
            'join_request_status',
            'created_at',
        ]

    def get_created_by_name(self, obj):
        return obj.created_by.name or obj.created_by.phone_number

    def get_member_count(self, obj):
        # Use annotated value when available (avoids extra query)
        if hasattr(obj, 'annotated_member_count'):
            return obj.annotated_member_count
        return obj.memberships.filter(is_active=True).count()

    def _request_user(self):
        request = self.context.get('request')
        return request.user if request else None

    def get_is_member(self, obj):
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return False
        return obj.memberships.filter(user=user, is_active=True).exists()

    def get_join_request_status(self, obj):
        """Returns 'PENDING' | 'APPROVED' | 'REJECTED' | None."""
        user = self._request_user()
        if user is None or not user.is_authenticated:
            return None
        req = obj.join_requests.filter(requester=user).order_by('-created_at').first()
        return req.status if req else None


class CommunityMembershipSerializer(serializers.ModelSerializer):

    phone_number = serializers.CharField(source='user.phone_number', read_only=True)
    name = serializers.SerializerMethodField()
    profile_photo = serializers.ImageField(source='user.profile_photo', read_only=True)

    class Meta:
        model = CommunityMembership
        fields = [
            'id',
            'phone_number',
            'name',
            'profile_photo',
            'role',
            'is_active',
            'joined_at',
        ]

    def get_name(self, obj):
        return obj.user.name or obj.user.phone_number


class CommunityJoinRequestSerializer(serializers.ModelSerializer):
    requester_phone = serializers.CharField(source='requester.phone_number', read_only=True)
    requester_name = serializers.SerializerMethodField()
    community_name = serializers.CharField(source='community.name', read_only=True)

    class Meta:
        model  = CommunityJoinRequest
        fields = ['id', 'community', 'community_name', 'requester_phone', 'requester_name', 'status', 'created_at']

    def get_requester_name(self, obj):
        return obj.requester.name or obj.requester.phone_number
