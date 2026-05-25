from rest_framework import serializers
from django.utils import timezone

from .models import Reminder


class ReminderSerializer(serializers.ModelSerializer):
    is_overdue = serializers.SerializerMethodField()

    class Meta:
        model  = Reminder
        fields = [
            'id', 'reminder_type', 'title', 'note',
            'contribution_id', 'community_id',
            'scheduled_for', 'recurrence', 'next_fire_at',
            'is_active', 'last_sent_at', 'send_count',
            'is_overdue', 'created_at',
        ]
        read_only_fields = ['next_fire_at', 'last_sent_at', 'send_count', 'is_overdue', 'created_at']

    def get_is_overdue(self, obj):
        return obj.is_active and obj.next_fire_at < timezone.now()


class ReminderCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Reminder
        fields = [
            'reminder_type', 'title', 'note',
            'contribution_id', 'community_id',
            'scheduled_for', 'recurrence',
        ]

    def validate_scheduled_for(self, value):
        if value <= timezone.now():
            raise serializers.ValidationError("scheduled_for must be in the future.")
        return value

    def create(self, validated_data):
        validated_data['next_fire_at'] = validated_data['scheduled_for']
        return super().create(validated_data)


class ReminderUpdateSerializer(serializers.ModelSerializer):
    class Meta:
        model  = Reminder
        fields = ['title', 'note', 'scheduled_for', 'recurrence', 'is_active']

    def update(self, instance, validated_data):
        # When rescheduling, reset next_fire_at to the new scheduled_for
        if 'scheduled_for' in validated_data:
            validated_data['next_fire_at'] = validated_data['scheduled_for']
        return super().update(instance, validated_data)
