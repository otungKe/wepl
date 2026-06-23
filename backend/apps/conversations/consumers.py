import json
import time

from channels.generic.websocket import AsyncWebsocketConsumer
from asgiref.sync import sync_to_async
from urllib.parse import parse_qs

from apps.communities.models import CommunityMembership
from apps.tenants.rls import tenant_context
from .groups import group_name
from .models import Conversation, Message
from .services import ConversationService


class ConversationConsumer(AsyncWebsocketConsumer):

    async def connect(self):
        self.conversation_id = self.scope['url_route']['kwargs']['conversation_id']
        self.tenant_id = None
        user = self.scope["user"]

        if user.is_anonymous:
            await self.close()
            return

        row = await sync_to_async(
            lambda: Conversation.objects.filter(id=self.conversation_id)
            .values_list('community_id', 'community__tenant_id').first()
        )()

        if not row or not row[0]:
            await self.close()
            return
        community_id, self.tenant_id = row

        # Tenant-scope the fan-out group so it can never collide across tenants.
        self.room_group_name = group_name(self.tenant_id, self.conversation_id)

        is_member = await sync_to_async(
            CommunityMembership.objects.filter(
                community_id=community_id, user=user, is_active=True
            ).exists
        )()

        if not is_member:
            await self.close()
            return

        # Record token expiry + session id so we can close the socket cleanly when
        # the token expires or the session is revoked. The JWT middleware already
        # validated the token (incl. the session) on connect — extract from scope.
        self._token_exp: int = 0
        self._sid = None
        qs = parse_qs(self.scope.get("query_string", b"").decode())
        raw_token = (qs.get("token") or [""])[0]
        if raw_token:
            try:
                from rest_framework_simplejwt.tokens import AccessToken
                from apps.users.sessions import SID_CLAIM
                tok = AccessToken(raw_token)
                self._token_exp = tok.payload.get("exp", 0)
                self._sid = tok.payload.get(SID_CLAIM)
            except Exception:
                pass

        await self.channel_layer.group_add(self.room_group_name, self.channel_name)
        await self.accept()

    async def disconnect(self, close_code):
        await self.channel_layer.group_discard(self.room_group_name, self.channel_name)

    async def receive(self, text_data):
        # ── Token expiry check ────────────────────────────────────────────────
        # Close the socket if the access token has expired.
        # The client must reconnect with a fresh token (obtained via the REST
        # token-refresh endpoint) to continue.
        if self._token_exp and time.time() > self._token_exp:
            await self.send(text_data=json.dumps({
                "type":    "session_expired",
                "message": "Your session has expired. Please reconnect with a fresh token.",
            }))
            await self.close(code=4001)   # 4001 = custom "session expired" code
            return

        data = json.loads(text_data)
        event_type = data.get("type", "message")
        user = self.scope["user"]

        # ── Ping / keepalive ──────────────────────────────────────────────────
        # Client sends {"type": "ping"} periodically. We reply with a pong so the
        # client knows the connection is alive. We also re-check the session here
        # (ADR-0010) — a low-frequency heartbeat — so a session revoked while the
        # socket is open is detected within one ping interval and the socket closed.
        if event_type == "ping":
            if self._sid and not await self._session_active():
                await self.send(text_data=json.dumps({
                    "type":    "session_expired",
                    "message": "Your session has been revoked. Please sign in again.",
                }))
                await self.close(code=4001)
                return
            await self.send(text_data=json.dumps({"type": "pong"}))
            return

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

        saved = await sync_to_async(self._create_message)(
            conversation_id=self.conversation_id,
            sender=user,
            content=message,
            reply_to_id=reply_to_id,
        )

        reply_to_data = None
        if reply_to_id:
            rt = await sync_to_async(self._fetch_reply)(reply_to_id)
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

    # ── Tenant-scoped DB helpers ──────────────────────────────────────────────
    # Wrap writes/reads in tenant_context so RLS applies on the worker thread's
    # connection for the duration of the operation (P6-04 follow-up).

    @staticmethod
    def _is_session_active(sid) -> bool:
        from apps.users.sessions import active_session
        return active_session(sid) is not None

    async def _session_active(self) -> bool:
        return await sync_to_async(self._is_session_active)(self._sid)

    def _create_message(self, **kwargs):
        with tenant_context(self.tenant_id):
            return ConversationService.create_message(**kwargs)

    def _fetch_reply(self, reply_to_id):
        with tenant_context(self.tenant_id):
            return Message.objects.select_related('sender').filter(id=reply_to_id).first()

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
