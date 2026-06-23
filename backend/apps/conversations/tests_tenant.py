"""Tenant-context tests for chat WS + the channel-group scoping (P6-04/P6-05).

Covers the two gaps the platform-hardening review flagged outside REST:
  * chat WebSocket fan-out groups must be tenant-scoped, and
  * the consumer must run its DB work inside the RLS tenant context.
"""
from asgiref.sync import async_to_sync, sync_to_async
from channels.routing import URLRouter
from channels.testing import WebsocketCommunicator
from django.contrib.auth import get_user_model
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.users.auth import STAGE_ACTIVE, issue_tokens

from .groups import group_name, group_for_conversation_id
from .jwt_middleware import JWTAuthMiddleware
from .models import Conversation, Message
from .routing import websocket_urlpatterns

User = get_user_model()
Role = CommunityMembership.Role

INMEMORY = {"default": {"BACKEND": "channels.layers.InMemoryChannelLayer"}}


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


class GroupNamingTests(TestCase):

    def test_group_name_is_tenant_scoped(self):
        self.assertEqual(group_name(7, 42), "conv_7_42")

    def test_group_for_conversation_id_resolves_tenant(self):
        creator = make_user("254700000001")
        community = CommunityService.create_community(creator, {"name": "Chama"})
        conv = Conversation.objects.create(
            community=community, topic="General", created_by=creator)
        self.assertEqual(
            group_for_conversation_id(conv.id),
            f"conv_{community.tenant_id}_{conv.id}",
        )

    def test_distinct_tenants_never_share_a_group(self):
        from apps.tenants.models import Tenant
        c1 = make_user("254700000001")
        c2 = make_user("254700000002")
        comm1 = CommunityService.create_community(c1, {"name": "A"})
        comm2 = Community = CommunityService.create_community(c2, {"name": "B"})
        # Force the two communities onto different tenants.
        t2 = Tenant.objects.create(slug="org-b", name="Org B")
        comm2.tenant = t2
        comm2.save(update_fields=["tenant"])
        conv1 = Conversation.objects.create(community=comm1, topic="x", created_by=c1)
        conv2 = Conversation.objects.create(community=comm2, topic="y", created_by=c2)
        self.assertNotEqual(
            group_for_conversation_id(conv1.id),
            group_for_conversation_id(conv2.id),
        )


class CeleryTenantHookTests(TestCase):
    """Task boundaries must reset the RLS tenant context (no leakage between tasks)."""

    def test_postrun_clears_pinned_tenant(self):
        from apps.tenants.rls import set_current_tenant, current_tenant_id
        from apps.tenants.celery_hooks import _on_postrun
        from apps.tenants.resolve import default_tenant

        set_current_tenant(default_tenant().id)
        self.assertIsNotNone(current_tenant_id())
        _on_postrun()
        self.assertIsNone(current_tenant_id())

    def test_prerun_clears_leaked_tenant(self):
        from apps.tenants.rls import set_current_tenant, current_tenant_id
        from apps.tenants.celery_hooks import _on_prerun
        from apps.tenants.resolve import default_tenant

        set_current_tenant(default_tenant().id)
        _on_prerun()
        self.assertIsNone(current_tenant_id())

    def test_hooks_are_registered(self):
        from celery.signals import task_prerun, task_postrun
        self.assertTrue(task_prerun.has_listeners())
        self.assertTrue(task_postrun.has_listeners())


@override_settings(CHANNEL_LAYERS=INMEMORY)
class ConsumerTenantTests(TransactionTestCase):
    """End-to-end: the consumer authenticates, joins the tenant-scoped group, and
    persists a message sent over the socket (exercising the tenant_context path)."""

    def test_message_round_trip_over_websocket(self):
        async_to_sync(self._round_trip)()

    def _setup(self):
        user = make_user("254700000001")
        community = CommunityService.create_community(user, {"name": "Chama"})
        conv = Conversation.objects.create(
            community=community, topic="General", created_by=user)
        access = issue_tokens(user, STAGE_ACTIVE)["access"]
        return conv.id, access

    async def _round_trip(self):
        conv_id, access = await sync_to_async(self._setup)()
        app = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        communicator = WebsocketCommunicator(
            app, f"/ws/conversation/{conv_id}/?token={access}")
        connected, _ = await communicator.connect()
        self.assertTrue(connected)

        # A fan-out to the *helper's* tenant-scoped group reaches this consumer —
        # proving the consumer and the REST senders agree on the scoped name.
        from channels.layers import get_channel_layer
        layer = get_channel_layer()
        grp = await sync_to_async(group_for_conversation_id)(conv_id)
        self.assertNotEqual(grp, f"conv_{conv_id}")  # tenant-scoped, not the bare name
        await layer.group_send(grp, {
            "type": "chat_message", "id": 0, "message": "via fan-out",
            "sender": "s", "sender_phone": "p", "created_at": "now",
        })
        fan = await communicator.receive_json_from(timeout=5)
        self.assertEqual(fan["message"], "via fan-out")

        await communicator.send_json_to({"message": "hello over ws"})
        reply = await communicator.receive_json_from(timeout=5)
        self.assertEqual(reply["type"], "message")
        self.assertEqual(reply["message"], "hello over ws")
        await communicator.disconnect()

        # message was persisted through the tenant_context-wrapped create path
        exists = await sync_to_async(
            Message.objects.filter(conversation_id=conv_id, content="hello over ws").exists
        )()
        self.assertTrue(exists)

    def test_outsider_is_rejected(self):
        async_to_sync(self._outsider)()

    async def _outsider(self):
        def setup():
            owner = make_user("254700000001")
            community = CommunityService.create_community(owner, {"name": "Chama"})
            conv = Conversation.objects.create(
                community=community, topic="General", created_by=owner)
            outsider = make_user("254700000099")  # not a member
            return conv.id, issue_tokens(outsider, STAGE_ACTIVE)["access"]

        conv_id, access = await sync_to_async(setup)()
        app = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        communicator = WebsocketCommunicator(
            app, f"/ws/conversation/{conv_id}/?token={access}")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)  # membership check closes the socket

    def test_revoked_session_cannot_open_socket(self):
        async_to_sync(self._revoked)()

    async def _revoked(self):
        from apps.users.models import UserSession

        def setup():
            user = make_user("254700000001")
            community = CommunityService.create_community(user, {"name": "Chama"})
            conv = Conversation.objects.create(
                community=community, topic="General", created_by=user)
            access = issue_tokens(user, STAGE_ACTIVE)["access"]
            # revoke the session that issue_tokens just created
            UserSession.objects.filter(user=user).update(revoked_at=timezone.now())
            return conv.id, access

        conv_id, access = await sync_to_async(setup)()
        app = JWTAuthMiddleware(URLRouter(websocket_urlpatterns))
        communicator = WebsocketCommunicator(
            app, f"/ws/conversation/{conv_id}/?token={access}")
        connected, _ = await communicator.connect()
        self.assertFalse(connected)  # ADR-0010 session check rejects the handshake
