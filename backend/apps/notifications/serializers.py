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
        if obj.join_request_id is None:
            return None
        from apps.communities.models import CommunityJoinRequest
        try:
            return CommunityJoinRequest.objects.values_list('status', flat=True).get(id=obj.join_request_id)
        except CommunityJoinRequest.DoesNotExist:
            return None
