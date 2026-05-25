from django.shortcuts import get_object_or_404

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated
from rest_framework import status

from apps.communities.models import Community, CommunityMembership

from .models import Conversation, Message, MessageReaction
from .serializers import ConversationSerializer, MessageSerializer
from .services import ConversationService


class CommunityConversationsView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, community_id):
        get_object_or_404(Community, id=community_id)
        conversations = ConversationService.list_for_community(community_id)
        return Response(ConversationSerializer(conversations, many=True, context={'request': request}).data)

    def post(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        topic = (request.data.get('topic') or '').strip()
        if not topic:
            return Response({"error": "topic is required"}, status=status.HTTP_400_BAD_REQUEST)
        conv = ConversationService.create_conversation(
            user=request.user, community=community, topic=topic,
            photo=request.FILES.get('photo'),
        )
        return Response(ConversationSerializer(conv).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        return Response(ConversationSerializer(conv, context={'request': request}).data)

    def delete(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        ConversationService.delete_conversation(conv, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationMessagesView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, conversation_id):
        messages = ConversationService.get_messages(conversation_id, request.user)
        return Response(MessageSerializer(messages, many=True, context={'request': request}).data)

    def post(self, request, conversation_id):
        content = (request.data.get('content') or '').strip()
        attachment = request.FILES.get('attachment')
        if not content and not attachment:
            return Response({"error": "content or attachment is required"}, status=status.HTTP_400_BAD_REQUEST)

        requested_type = request.data.get('message_type', '').strip()
        if requested_type in ('voice', 'video', 'image') and attachment:
            message_type = requested_type
        else:
            message_type = 'image' if attachment else 'text'

        reply_to_id = request.data.get('reply_to_id') or None
        msg = ConversationService.create_message(
            conversation_id=conversation_id, sender=request.user, content=content,
            message_type=message_type, attachment=attachment, reply_to_id=reply_to_id,
        )

        attachment_url = request.build_absolute_uri(msg.attachment.url) if msg.attachment else None

        reply_to_data = None
        if msg.reply_to_id:
            rt = Message.objects.select_related('sender').filter(id=msg.reply_to_id).first()
            if rt and not rt.is_deleted:
                rt_attach = request.build_absolute_uri(rt.attachment.url) if rt.attachment else None
                rt_sender = rt.sender.name or f"User ...{rt.sender.phone_number[-4:]}"
                reply_to_data = {'id': rt.id, 'deleted': False, 'sender': rt_sender, 'content': rt.content, 'message_type': rt.message_type, 'attachment': rt_attach}
            elif rt:
                reply_to_data = {'id': rt.id, 'deleted': True, 'sender': '', 'content': '', 'message_type': 'text', 'attachment': None}

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'conv_{conversation_id}',
            {
                "type": "chat_message",
                "id": msg.id,
                "message": msg.content,
                "sender": msg.sender.name or f"User ...{msg.sender.phone_number[-4:]}",
                "sender_phone": msg.sender.phone_number,
                "created_at": str(msg.created_at),
                "message_type": msg.message_type,
                "attachment": attachment_url,
                "reply_to": reply_to_data,
                "reactions": {},
                "is_edited": False,
            }
        )
        return Response(MessageSerializer(msg, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ConversationDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        if conv.created_by != request.user:
            return Response({"error": "Only the creator can delete this conversation."}, status=status.HTTP_403_FORBIDDEN)
        conv.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarkConversationReadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        get_object_or_404(Conversation, id=conversation_id)
        ConversationService.mark_read(conversation_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnreadConversationsCountView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(ConversationService.get_unread_summary(request.user))


def _can_delete_message(user, message):
    """True if user is the sender, community creator, or community admin."""
    if message.sender == user:
        return True
    community = message.conversation.community
    if community.created_by == user:
        return True
    return CommunityMembership.objects.filter(
        community=community, user=user, role='admin', is_active=True
    ).exists()


class MessageDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request, message_id):
        message = get_object_or_404(Message, id=message_id)
        if not _can_delete_message(request.user, message):
            return Response({"error": "You don't have permission to delete this message."}, status=status.HTTP_403_FORBIDDEN)
        message.is_deleted = True
        message.save(update_fields=["is_deleted"])

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'conv_{message.conversation_id}',
            {"type": "message_delete", "id": message.id}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageBulkDeleteView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, conversation_id):
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response({"error": "ids must be a non-empty list"}, status=status.HTTP_400_BAD_REQUEST)

        messages = Message.objects.select_related('sender', 'conversation__community').filter(
            id__in=ids, conversation_id=conversation_id, is_deleted=False
        )
        deleted_ids = []
        for msg in messages:
            if _can_delete_message(request.user, msg):
                msg.is_deleted = True
                msg.save(update_fields=['is_deleted'])
                deleted_ids.append(msg.id)

        channel_layer = get_channel_layer()
        for mid in deleted_ids:
            async_to_sync(channel_layer.group_send)(
                f'conv_{conversation_id}',
                {"type": "message_delete", "id": mid}
            )

        return Response({"deleted": deleted_ids})


class MessageEditView(APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request, message_id):
        message = get_object_or_404(Message, id=message_id)
        if message.sender != request.user:
            return Response({"error": "Only the sender can edit this message."}, status=status.HTTP_403_FORBIDDEN)
        content = (request.data.get('content') or '').strip()
        if not content:
            return Response({"error": "content is required"}, status=status.HTTP_400_BAD_REQUEST)
        message.content = content
        message.is_edited = True
        message.save(update_fields=['content', 'is_edited'])

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'conv_{message.conversation_id}',
            {"type": "message_edit", "id": message.id, "content": message.content}
        )
        return Response({"id": message.id, "content": message.content, "is_edited": True})


class MessageReactView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, message_id):
        message = get_object_or_404(Message, id=message_id)
        emoji = (request.data.get('emoji') or '').strip()
        if not emoji:
            return Response({"error": "emoji is required"}, status=status.HTTP_400_BAD_REQUEST)

        existing = MessageReaction.objects.filter(message=message, user=request.user).first()
        if existing:
            if existing.emoji == emoji:
                existing.delete()
                action = 'remove'
            else:
                existing.emoji = emoji
                existing.save(update_fields=['emoji'])
                action = 'update'
        else:
            MessageReaction.objects.create(message=message, user=request.user, emoji=emoji)
            action = 'add'

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            f'conv_{message.conversation_id}',
            {
                "type": "reaction_event",
                "message_id": message.id,
                "emoji": emoji,
                "sender_phone": request.user.phone_number,
                "action": action,
            }
        )
        return Response({"action": action})
