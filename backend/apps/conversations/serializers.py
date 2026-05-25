from rest_framework import serializers
from .models import Conversation, ConversationReadStatus, Message


class ConversationSerializer(serializers.ModelSerializer):

    created_by = serializers.CharField(source='created_by.phone_number', read_only=True)
    message_count = serializers.SerializerMethodField()
    last_message = serializers.SerializerMethodField()
    unread_count = serializers.SerializerMethodField()

    class Meta:
        model = Conversation
        fields = [
            'id', 'community', 'topic', 'photo', 'created_by',
            'created_at', 'message_count', 'last_message', 'unread_count',
        ]
        extra_kwargs = {'community': {'read_only': True}}

    def get_message_count(self, obj):
        return obj.messages.filter(is_deleted=False).count()

    def get_last_message(self, obj):
        last = obj.messages.filter(is_deleted=False).order_by('-created_at').first()
        if not last:
            return None
        return {
            'content': last.content,
            'sender': last.sender.name or last.sender.phone_number,
            'created_at': last.created_at,
            'message_type': last.message_type,
        }

    def get_unread_count(self, obj):
        request = self.context.get('request')
        if not request or not request.user.is_authenticated:
            return 0
        user = request.user
        read_status = ConversationReadStatus.objects.filter(conversation=obj, user=user).first()
        qs = obj.messages.filter(is_deleted=False).exclude(sender=user)
        if read_status:
            qs = qs.filter(created_at__gt=read_status.last_read_at)
        return qs.count()


class MessageSerializer(serializers.ModelSerializer):

    sender = serializers.SerializerMethodField()
    sender_phone = serializers.CharField(source='sender.phone_number', read_only=True)
    attachment = serializers.SerializerMethodField()
    reply_to = serializers.SerializerMethodField()
    reactions = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = [
            'id', 'sender', 'sender_phone', 'content', 'message_type',
            'attachment', 'reply_to', 'reactions', 'is_edited', 'created_at',
        ]

    def get_sender(self, obj):
        if obj.sender.name:
            return obj.sender.name
        phone = obj.sender.phone_number
        return f"User ...{phone[-4:]}" if len(phone) >= 4 else phone

    def get_attachment(self, obj):
        if not obj.attachment:
            return None
        request = self.context.get('request')
        if request:
            return request.build_absolute_uri(obj.attachment.url)
        return obj.attachment.url

    def get_reply_to(self, obj):
        if not obj.reply_to:
            return None
        rt = obj.reply_to
        if rt.is_deleted:
            return {'id': rt.id, 'deleted': True, 'sender': '', 'content': '', 'message_type': 'text', 'attachment': None}
        request = self.context.get('request')
        attachment_url = None
        if rt.attachment:
            attachment_url = request.build_absolute_uri(rt.attachment.url) if request else rt.attachment.url
        sender = rt.sender.name or (f"User ...{rt.sender.phone_number[-4:]}" if len(rt.sender.phone_number) >= 4 else rt.sender.phone_number)
        return {
            'id': rt.id, 'deleted': False, 'sender': sender,
            'content': rt.content, 'message_type': rt.message_type, 'attachment': attachment_url,
        }

    def get_reactions(self, obj):
        result = {}
        for r in obj.reactions.all():
            result.setdefault(r.emoji, []).append(r.user.phone_number)
        return result
