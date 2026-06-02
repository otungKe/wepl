import logging

from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Conversation, Message, ConversationReadStatus
from apps.communities.models import Community, CommunityMembership

logger = logging.getLogger(__name__)


class ConversationService:

    @staticmethod
    def create_conversation(user, community, topic, photo=None):
        if not CommunityMembership.objects.filter(
            community=community, user=user, is_active=True
        ).exists():
            raise PermissionDenied("You are not a member of this community.")

        conversation = Conversation.objects.create(
            community=community,
            topic=topic,
            photo=photo,
            created_by=user,
        )
        logger.info(
            "ConversationService.create_conversation: user %s created conversation %s "
            "in community %s (topic=%r)",
            user.id, conversation.id, community.id, topic,
        )
        return conversation

    @staticmethod
    def list_for_community(community_id):
        return (
            Conversation.objects
            .filter(community_id=community_id)
            .annotate(last_msg_at=Coalesce(Max('messages__created_at'), 'created_at'))
            .order_by('-last_msg_at')
        )

    @staticmethod
    def create_message(conversation_id, sender, content, message_type='text', attachment=None, reply_to_id=None):
        conversation = get_object_or_404(Conversation, id=conversation_id)

        if not CommunityMembership.objects.filter(
            community=conversation.community,
            user=sender,
            is_active=True,
        ).exists():
            logger.warning(
                "ConversationService.create_message: user %s attempted to send a message "
                "in conversation %s without community membership",
                sender.id, conversation_id,
            )
            raise PermissionDenied("Not a member of this community.")

        msg = Message.objects.create(
            conversation=conversation,
            sender=sender,
            content=content,
            message_type=message_type,
            attachment=attachment,
            reply_to_id=reply_to_id,
        )
        logger.info(
            "ConversationService.create_message: user %s sent message %s "
            "in conversation %s (type=%s)",
            sender.id, msg.id, conversation_id, message_type,
        )
        return msg

    @staticmethod
    def get_messages(conversation_id, user):
        conversation = get_object_or_404(Conversation, id=conversation_id)
        membership = CommunityMembership.objects.filter(
            community=conversation.community, user=user, is_active=True
        ).first()
        qs = Message.objects.select_related('sender', 'reply_to__sender').prefetch_related('reactions__user').filter(
            conversation_id=conversation_id, is_deleted=False
        )
        if membership:
            qs = qs.filter(created_at__gte=membership.joined_at)
        return qs.order_by('created_at')

    @staticmethod
    def mark_read(conversation_id, user):
        ConversationReadStatus.objects.update_or_create(
            conversation_id=conversation_id,
            user=user,
            defaults={'last_read_at': timezone.now()},
        )

    @staticmethod
    def get_unread_summary(user):
        """
        Returns {'total': N, 'by_community': {community_id: unread_count, ...}}
        counting only messages not sent by the user.
        """
        community_ids = list(
            CommunityMembership.objects.filter(user=user, is_active=True)
            .values_list('community_id', flat=True)
        )
        conversations = Conversation.objects.filter(community_id__in=community_ids)
        read_statuses = {
            rs.conversation_id: rs.last_read_at
            for rs in ConversationReadStatus.objects.filter(
                conversation__in=conversations, user=user
            )
        }

        by_community: dict[int, int] = {}
        for conv in conversations:
            qs = conv.messages.filter(is_deleted=False).exclude(sender=user)
            last_read = read_statuses.get(conv.id)
            if last_read:
                qs = qs.filter(created_at__gt=last_read)
            count = qs.count()
            if count:
                by_community[conv.community_id] = by_community.get(conv.community_id, 0) + count

        return {
            'total': sum(by_community.values()),
            'by_community': {str(k): v for k, v in by_community.items()},
        }

    @staticmethod
    def delete_conversation(conversation, user):
        if conversation.created_by != user:
            is_admin = CommunityMembership.objects.filter(
                community=conversation.community,
                user=user,
                role='admin',
                is_active=True,
            ).exists()
            if not is_admin:
                logger.warning(
                    "ConversationService.delete_conversation: user %s unauthorized delete "
                    "attempt on conversation %s",
                    user.id, conversation.id,
                )
                raise PermissionDenied("Only the creator or a community admin can delete this conversation.")
        logger.info(
            "ConversationService.delete_conversation: user %s deleted conversation %s "
            "in community %s",
            user.id, conversation.id, conversation.community_id,
        )
        conversation.delete()
