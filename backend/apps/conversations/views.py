import logging

from django.shortcuts import get_object_or_404

from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.communities.models import Community
from apps.core.policy import can
from apps.users.auth import IsActiveSession

from .groups import group_for_conversation_id
from .models import Conversation, Message, MessageReaction
from .serializers import ConversationSerializer, MessageSerializer
from .services import ConversationService

logger = logging.getLogger(__name__)

# Hard cap on bulk-delete payload to prevent DoS
_BULK_DELETE_MAX = 100


def _is_community_member(community, user) -> bool:
    """True if user is the community creator or an active member (ADR-0009)."""
    return can(user, "community.view", community)


def _can_delete_message(user, message) -> bool:
    """True if user is the sender, community creator, or community admin (ADR-0009)."""
    return can(user, "message.delete", message)


class CommunityConversationsView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, community_id):
        community = get_object_or_404(Community, id=community_id)
        if not _is_community_member(community, request.user):
            logger.warning(
                "CommunityConversationsView.get: user %s attempted to list conversations "
                "for community %s without membership",
                request.user.id, community_id,
            )
            return Response(
                {"error": "You must be a member of this community to view its conversations."},
                status=status.HTTP_403_FORBIDDEN,
            )
        conversations = ConversationService.list_for_community(community_id)
        logger.info(
            "CommunityConversationsView.get: user %s listed conversations for community %s",
            request.user.id, community_id,
        )
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
        logger.info(
            "CommunityConversationsView.post: user %s created conversation %s in community %s",
            request.user.id, conv.id, community_id,
        )
        return Response(ConversationSerializer(conv).data, status=status.HTTP_201_CREATED)


class ConversationDetailView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        if not _is_community_member(conv.community, request.user):
            logger.warning(
                "ConversationDetailView.get: user %s attempted to access conversation %s "
                "without community membership",
                request.user.id, conversation_id,
            )
            return Response(
                {"error": "You must be a member of this community to view this conversation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return Response(ConversationSerializer(conv, context={'request': request}).data)

    def delete(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        ConversationService.delete_conversation(conv, request.user)
        logger.info(
            "ConversationDetailView.delete: user %s deleted conversation %s",
            request.user.id, conversation_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConversationMessagesView(APIView):
    permission_classes = [IsActiveSession]

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

        logger.info(
            "ConversationMessagesView.post: user %s sent message %s in conversation %s (type=%s)",
            request.user.id, msg.id, conversation_id, message_type,
        )

        attachment_url = request.build_absolute_uri(msg.attachment.url) if msg.attachment else None

        reply_to_data = None
        if msg.reply_to_id:
            rt = Message.objects.select_related('sender').filter(id=msg.reply_to_id).first()
            if rt and not rt.is_deleted:
                rt_attach = request.build_absolute_uri(rt.attachment.url) if rt.attachment else None
                rt_sender = rt.sender.name or f"User ...{rt.sender.phone_number[-4:]}"
                reply_to_data = {
                    'id': rt.id, 'deleted': False, 'sender': rt_sender,
                    'content': rt.content, 'message_type': rt.message_type, 'attachment': rt_attach,
                }
            elif rt:
                reply_to_data = {
                    'id': rt.id, 'deleted': True, 'sender': '', 'content': '',
                    'message_type': 'text', 'attachment': None,
                }

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_for_conversation_id(conversation_id),
            {
                "type":         "chat_message",
                "id":           msg.id,
                "message":      msg.content,
                "sender":       msg.sender.name or f"User ...{msg.sender.phone_number[-4:]}",
                "sender_phone": msg.sender.phone_number,
                "created_at":   str(msg.created_at),
                "message_type": msg.message_type,
                "attachment":   attachment_url,
                "reply_to":     reply_to_data,
                "reactions":    {},
                "is_edited":    False,
            }
        )
        return Response(MessageSerializer(msg, context={'request': request}).data, status=status.HTTP_201_CREATED)


class ConversationDeleteView(APIView):
    permission_classes = [IsActiveSession]

    def delete(self, request, conversation_id):
        conv = get_object_or_404(Conversation, id=conversation_id)
        if conv.created_by != request.user:
            return Response(
                {"error": "Only the creator can delete this conversation."},
                status=status.HTTP_403_FORBIDDEN,
            )
        conv.delete()
        logger.info(
            "ConversationDeleteView: user %s deleted conversation %s",
            request.user.id, conversation_id,
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MarkConversationReadView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, conversation_id):
        get_object_or_404(Conversation, id=conversation_id)
        ConversationService.mark_read(conversation_id, request.user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UnreadConversationsCountView(APIView):
    permission_classes = [IsActiveSession]

    def get(self, request):
        return Response(ConversationService.get_unread_summary(request.user))


class MessageDeleteView(APIView):
    permission_classes = [IsActiveSession]

    def delete(self, request, message_id):
        message = get_object_or_404(Message, id=message_id)
        if not _can_delete_message(request.user, message):
            logger.warning(
                "MessageDeleteView: user %s unauthorized delete attempt on message %s",
                request.user.id, message_id,
            )
            return Response(
                {"error": "You don't have permission to delete this message."},
                status=status.HTTP_403_FORBIDDEN,
            )
        message.is_deleted = True
        message.save(update_fields=["is_deleted"])
        logger.info(
            "MessageDeleteView: user %s deleted message %s in conversation %s",
            request.user.id, message_id, message.conversation_id,
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_for_conversation_id(message.conversation_id),
            {"type": "message_delete", "id": message.id}
        )
        return Response(status=status.HTTP_204_NO_CONTENT)


class MessageBulkDeleteView(APIView):
    permission_classes = [IsActiveSession]

    def post(self, request, conversation_id):
        ids = request.data.get('ids', [])
        if not ids or not isinstance(ids, list):
            return Response(
                {"error": "ids must be a non-empty list"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        # Cap payload size to prevent DoS
        if len(ids) > _BULK_DELETE_MAX:
            return Response(
                {"error": f"Cannot delete more than {_BULK_DELETE_MAX} messages at once."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        messages = Message.objects.select_related(
            'sender', 'conversation__community'
        ).filter(
            id__in=ids, conversation_id=conversation_id, is_deleted=False
        )

        to_delete = [msg for msg in messages if _can_delete_message(request.user, msg)]
        deleted_ids = [msg.id for msg in to_delete]

        if to_delete:
            # Single bulk_update instead of N individual saves
            for msg in to_delete:
                msg.is_deleted = True
            Message.objects.bulk_update(to_delete, ['is_deleted'])

        logger.info(
            "MessageBulkDeleteView: user %s bulk-deleted %d messages in conversation %s",
            request.user.id, len(deleted_ids), conversation_id,
        )

        channel_layer = get_channel_layer()
        for mid in deleted_ids:
            async_to_sync(channel_layer.group_send)(
                group_for_conversation_id(conversation_id),
                {"type": "message_delete", "id": mid}
            )

        return Response({"deleted": deleted_ids})


class MessageEditView(APIView):
    permission_classes = [IsActiveSession]

    def patch(self, request, message_id):
        message = get_object_or_404(Message, id=message_id)
        if not can(request.user, "message.edit", message):
            logger.warning(
                "MessageEditView: user %s attempted to edit message %s sent by user %s",
                request.user.id, message_id, message.sender_id,
            )
            return Response(
                {"error": "Only the sender can edit this message."},
                status=status.HTTP_403_FORBIDDEN,
            )
        content = (request.data.get('content') or '').strip()
        if not content:
            return Response({"error": "content is required"}, status=status.HTTP_400_BAD_REQUEST)
        message.content = content
        message.is_edited = True
        message.save(update_fields=['content', 'is_edited'])
        logger.info(
            "MessageEditView: user %s edited message %s in conversation %s",
            request.user.id, message_id, message.conversation_id,
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_for_conversation_id(message.conversation_id),
            {"type": "message_edit", "id": message.id, "content": message.content}
        )
        return Response({"id": message.id, "content": message.content, "is_edited": True})


class MessageReactView(APIView):
    permission_classes = [IsActiveSession]

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

        logger.info(
            "MessageReactView: user %s %sd reaction '%s' on message %s",
            request.user.id, action, emoji, message_id,
        )

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            group_for_conversation_id(message.conversation_id),
            {
                "type":         "reaction_event",
                "message_id":   message.id,
                "emoji":        emoji,
                "sender_phone": request.user.phone_number,
                "action":       action,
            }
        )
        return Response({"action": action})
