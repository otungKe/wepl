from rest_framework import serializers
from .models import Notification


class NotificationSerializer(serializers.ModelSerializer):
    join_request_status = serializers.SerializerMethodField()

    class Meta:
        model = Notification
        fields = [
            'id',
            'notification_type',
            'title',
            'message',
            'is_read',
            'community_id',
            'conversation_id',
            'contribution_id',
            'join_request_id',
            'join_request_status',
            'created_at',
        ]

    def get_join_request_status(self, obj):
        """
        Return the live status of the join request referenced by this notification.
        Checks both CommunityJoinRequest and ContributionJoinRequest so that inline
        action buttons on the notifications screen show the correct state.
        """
        if obj.join_request_id is None:
            return None

        # Community join requests
        if obj.notification_type in (
            'join_request', 'join_approved', 'join_rejected',
        ):
            from apps.communities.models import CommunityJoinRequest
            try:
                return CommunityJoinRequest.objects.values_list(
                    'status', flat=True
                ).get(id=obj.join_request_id)
            except CommunityJoinRequest.DoesNotExist:
                return None

        # Contribution join requests and invitations
        if obj.notification_type in (
            'contribution_join_request', 'contribution_invite',
            'contribution_join_approved', 'contribution_join_rejected',
            'contribution_invite_accepted',
        ):
            from apps.contributions.models import ContributionJoinRequest
            try:
                return ContributionJoinRequest.objects.values_list(
                    'status', flat=True
                ).get(id=obj.join_request_id)
            except ContributionJoinRequest.DoesNotExist:
                return None

        return None
