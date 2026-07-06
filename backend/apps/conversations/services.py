import logging

from django.core.exceptions import PermissionDenied
from django.db.models import Max
from django.db.models.functions import Coalesce
from django.shortcuts import get_object_or_404
from django.utils import timezone

from apps.core.policy import can, require
from apps.users.tiers import AccessPolicy

from .models import Conversation, Message, ConversationReadStatus
from apps.communities.models import Community, CommunityMembership

logger = logging.getLogger(__name__)


class ConversationService:

    @staticmethod
    def create_conversation(user, community, topic, photo=None):
        AccessPolicy.gate(user, "Verify your identity to start conversations.")
        require(user, "community.view", community,
                "You are not a member of this community.")
        from apps.communities.services import require_active_community
        require_active_community(community, 'start a conversation')

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

        AccessPolicy.gate(sender, "Verify your identity to chat.")
        if not can(sender, "conversation.view", conversation):
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
        # Advance the high-water-mark to the latest message in the conversation
        # (ADR-0012) so unread counts are an exact, cheap id comparison.
        latest_id = (
            Message.objects.filter(conversation_id=conversation_id)
            .order_by('-id').values_list('id', flat=True).first()
        )
        ConversationReadStatus.objects.update_or_create(
            conversation_id=conversation_id,
            user=user,
            defaults={
                'last_read_at': timezone.now(),
                'last_read_message_id': latest_id,
            },
        )

    @staticmethod
    def get_unread_summary(user):
        """
        Returns {'total': N, 'by_community': {community_id: unread_count, ...}}
        counting only messages not sent by the user.

        One aggregate query (ADR-0012): each message is compared against the
        per-conversation read high-water-mark via a correlated subquery, then
        grouped by community — no per-conversation N+1 COUNT loop.
        """
        from django.db.models import Count, F, IntegerField, OuterRef, Subquery, Value
        from django.db.models.functions import Coalesce

        community_ids = list(
            CommunityMembership.objects.filter(user=user, is_active=True)
            .values_list('community_id', flat=True)
        )
        if not community_ids:
            return {'total': 0, 'by_community': {}}

        high_water = (
            ConversationReadStatus.objects
            .filter(conversation_id=OuterRef('conversation_id'), user=user)
            .values('last_read_message_id')[:1]
        )
        rows = (
            Message.objects
            .filter(conversation__community_id__in=community_ids, is_deleted=False)
            .exclude(sender=user)
            .annotate(hw=Coalesce(Subquery(high_water, output_field=IntegerField()), Value(0)))
            .filter(id__gt=F('hw'))
            .values('conversation__community_id')
            .annotate(n=Count('id'))
        )
        by_community = {str(r['conversation__community_id']): r['n'] for r in rows}
        return {
            'total': sum(by_community.values()),
            'by_community': by_community,
        }

    @staticmethod
    def delete_conversation(conversation, user):
        if not can(user, "conversation.delete", conversation):
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
