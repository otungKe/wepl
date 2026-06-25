from rest_framework import serializers
from .models import Activity


class ActivitySerializer(serializers.ModelSerializer):
    user = serializers.SerializerMethodField()

    class Meta:
        model = Activity
        fields = [
            'id',
            'user',
            'activity_type',
            'message',
            'visibility',
            'community',
            'created_at',
        ]

    def get_user(self, obj) -> str:
        u = obj.user
        return (getattr(u, 'name', '') or '').strip() or u.phone_number