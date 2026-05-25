import json

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async

from apps.communities.models import CommunityMembership
from .models import Conversation, Message
from .services import ConversationService


class ConversationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.room_group_name = f'conv_{self.conversation_id}'
        user = self.scope["user"]

        if user.is_anonymous:
            await self.close()
            return

        community_id = await sync_to_async(
            lambda: Conversation.objects.filter(id=self.conversation_id)
            .values_list('community_id', flat=True).first()
        )()

        if not community_id:
            await self.close()
            return

        is_member = await sync_to_async(
            CommunityMembership.objects.filter(
                community_id=community_id, user=user, is_active=True
            ).exists
        )()

        if not is_member:
            await self.close()
            return

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        data = json.loads(text_data)
        event_type = data.get("type", "message")
        user = self.scope["user"]

        # ── Typing indicator ──────────────────────────────────────────────────
        if event_type == "typing":
            sender_name = user.name or f"User ...{user.phone_number[-4:]}"
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    "type": "typing_event",
                    "sender": sender_name,
                    "sender_phone": user.phone_number,
                }
            )
            return

        # ── Text message ──────────────────────────────────────────────────────
        message = data.get("message")
        reply_to_id = data.get("reply_to_id")

        if not message:
            return

        saved = await sync_to_async(ConversationService.create_message)(
            conversation_id=self.conversation_id,
            sender=user,
            content=message,
            reply_to_id=reply_to_id,
        )

        reply_to_data = None
        if reply_to_id:
            rt = await sync_to_async(
                lambda: Message.objects.select_related('sender').filter(id=reply_to_id).first()
            )()
            if rt and not rt.is_deleted:
                rt_sender = rt.sender.name or f"User ...{rt.sender.phone_number[-4:]}"
                reply_to_data = {
                    'id': rt.id, 'deleted': False, 'sender': rt_sender,
                    'content': rt.content, 'message_type': rt.message_type, 'attachment': None,
                }
            elif rt:
                reply_to_data = {'id': rt.id, 'deleted': True, 'sender': '', 'content': '', 'message_type': 'text', 'attachment': None}

        await self.channel_layer.group_send(
            self.room_group_name,
            {
                "type": "chat_message",
                "id": saved.id,
                "message": saved.content,
                "sender": saved.sender.name or f"User ...{saved.sender.phone_number[-4:]}",
                "sender_phone": saved.sender.phone_number,
                "created_at": str(saved.created_at),
                "message_type": saved.message_type,
                "attachment": None,
                "reply_to": reply_to_data,
                "reactions": {},
                "is_edited": False,
            }
        )

    # ── Group-send handlers ───────────────────────────────────────────────────

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            "type": "message",
            "id": event.get("id"),
            "message": event["message"],
            "sender": event["sender"],
            "sender_phone": event["sender_phone"],
            "created_at": event["created_at"],
            "message_type": event.get("message_type", "text"),
            "attachment": event.get("attachment"),
            "reply_to": event.get("reply_to"),
            "reactions": event.get("reactions", {}),
            "is_edited": event.get("is_edited", False),
        }))

    async def typing_event(self, event):
        await self.send(text_data=json.dumps({
            "type": "typing",
            "sender": event["sender"],
            "sender_phone": event["sender_phone"],
        }))

    async def message_edit(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_edited",
            "id": event["id"],
            "content": event["content"],
        }))

    async def reaction_event(self, event):
        await self.send(text_data=json.dumps({
            "type": "reaction",
            "message_id": event["message_id"],
            "emoji": event["emoji"],
            "sender_phone": event["sender_phone"],
            "action": event["action"],
        }))

    async def message_delete(self, event):
        await self.send(text_data=json.dumps({
            "type": "message_deleted",
            "id": event["id"],
        }))
