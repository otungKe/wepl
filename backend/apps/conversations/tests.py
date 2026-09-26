"""Conversation/message authorization tests (ADR-0009).

The conversations app previously had no tests. These cover the policy
(unit + over-the-wire) that replaced the inline community-membership /
admin / sender checks.
"""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.core.policy import can
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

from .models import Conversation, Message

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def active_client(user) -> APIClient:
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class ConversationPolicyUnitTests(TestCase):

    def setUp(self):
        self.creator   = make_user("254700000001")   # community creator (admin)
        self.admin     = make_user("254700000002")
        self.treasurer = make_user("254700000003")
        self.member    = make_user("254700000004")
        self.outsider  = make_user("254700000005")

        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.admin,     community=self.community, role=Role.ADMIN)
        CommunityMembership.objects.create(user=self.treasurer, community=self.community, role=Role.TREASURER)
        CommunityMembership.objects.create(user=self.member,    community=self.community, role=Role.MEMBER)

        # conversation started by an ordinary member
        self.conv = Conversation.objects.create(
            community=self.community, topic="General", created_by=self.member)
        self.msg = Message.objects.create(
            conversation=self.conv, sender=self.member, content="hi")

    def test_view_is_community_membership(self):
        for u in (self.creator, self.admin, self.treasurer, self.member):
            self.assertTrue(can(u, "conversation.view", self.conv), u.phone_number)
        self.assertFalse(can(self.outsider, "conversation.view", self.conv))

    def test_delete_is_conv_creator_or_community_admin(self):
        # conversation creator
        self.assertTrue(can(self.member, "conversation.delete", self.conv))
        # community admin / creator
        self.assertTrue(can(self.admin, "conversation.delete", self.conv))
        self.assertTrue(can(self.creator, "conversation.delete", self.conv))
        # treasurer is NOT a moderator (historical role='admin' rule)
        self.assertFalse(can(self.treasurer, "conversation.delete", self.conv))
        self.assertFalse(can(self.outsider, "conversation.delete", self.conv))

    def test_message_edit_is_sender_only(self):
        self.assertTrue(can(self.member, "message.edit", self.msg))
        self.assertFalse(can(self.admin, "message.edit", self.msg))
        self.assertFalse(can(self.creator, "message.edit", self.msg))

    def test_message_delete_is_sender_or_admin(self):
        self.assertTrue(can(self.member, "message.delete", self.msg))   # sender
        self.assertTrue(can(self.admin, "message.delete", self.msg))    # community admin
        self.assertTrue(can(self.creator, "message.delete", self.msg))  # community creator
        self.assertFalse(can(self.treasurer, "message.delete", self.msg))
        self.assertFalse(can(self.outsider, "message.delete", self.msg))


class ConversationAuthzApiTests(TestCase):

    def setUp(self):
        self.creator  = make_user("254700000001")
        self.member   = make_user("254700000002")
        self.outsider = make_user("254700000003")
        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.member, community=self.community, role=Role.MEMBER)
        self.conv = Conversation.objects.create(
            community=self.community, topic="General", created_by=self.creator)
        self.msg = Message.objects.create(
            conversation=self.conv, sender=self.member, content="hi")

    def test_outsider_cannot_list_conversations(self):
        r = active_client(self.outsider).get(
            f"/api/conversations/community/{self.community.id}/")
        self.assertEqual(r.status_code, 403)

    def test_member_can_list_conversations(self):
        r = active_client(self.member).get(
            f"/api/conversations/community/{self.community.id}/")
        self.assertEqual(r.status_code, 200)

    def test_outsider_cannot_view_conversation_detail(self):
        r = active_client(self.outsider).get(f"/api/conversations/{self.conv.id}/")
        self.assertEqual(r.status_code, 403)

    def test_non_sender_cannot_edit_message(self):
        r = active_client(self.creator).patch(
            f"/api/conversations/messages/{self.msg.id}/edit/",
            {"content": "tampered"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_sender_can_edit_own_message(self):
        r = active_client(self.member).patch(
            f"/api/conversations/messages/{self.msg.id}/edit/",
            {"content": "fixed typo"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.msg.refresh_from_db()
        self.assertEqual(self.msg.content, "fixed typo")
        self.assertTrue(self.msg.is_edited)

    def test_admin_can_delete_any_message(self):
        # creator is a community admin → may moderate another member's message
        r = active_client(self.creator).delete(
            f"/api/conversations/messages/{self.msg.id}/delete/")
        self.assertEqual(r.status_code, 204)
        self.msg.refresh_from_db()
        self.assertTrue(self.msg.is_deleted)

    def test_outsider_cannot_delete_message(self):
        r = active_client(self.outsider).delete(
            f"/api/conversations/messages/{self.msg.id}/delete/")
        self.assertEqual(r.status_code, 403)


class ConversationOutsiderApiTests(TestCase):
    """What a signed-in user from outside the group can reach by id."""

    def setUp(self):
        self.creator  = make_user("254700000011")
        self.member   = make_user("254700000012")
        self.outsider = make_user("254700000013")
        self.community = CommunityService.create_community(self.creator, {"name": "Private chama"})
        CommunityMembership.objects.create(user=self.member, community=self.community, role=Role.MEMBER)
        self.conv = Conversation.objects.create(
            community=self.community, topic="Payouts", created_by=self.member)
        self.secret = Message.objects.create(
            conversation=self.conv, sender=self.creator, content="secret payout plan")

        other = CommunityService.create_community(self.outsider, {"name": "Outsider chama"})
        self.own_conv = Conversation.objects.create(
            community=other, topic="Ours", created_by=self.outsider)

    def test_outsider_cannot_read_messages(self):
        r = active_client(self.outsider).get(f"/api/conversations/{self.conv.id}/messages/")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("secret payout plan", r.content.decode())

    def test_member_can_read_messages(self):
        r = active_client(self.member).get(f"/api/conversations/{self.conv.id}/messages/")
        self.assertEqual(r.status_code, 200)

    def test_reply_cannot_quote_another_groups_message(self):
        r = active_client(self.outsider).post(
            f"/api/conversations/{self.own_conv.id}/messages/",
            {"content": "quoting", "reply_to_id": self.secret.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertNotIn("secret payout plan", r.content.decode())
        self.assertIsNone(Message.objects.get(id=r.json()["id"]).reply_to_id)

    def test_reply_within_the_conversation_is_kept(self):
        r = active_client(self.creator).post(
            f"/api/conversations/{self.conv.id}/messages/",
            {"content": "agreed", "reply_to_id": self.secret.id}, format="json")
        self.assertEqual(r.status_code, 201, r.content)
        self.assertEqual(Message.objects.get(id=r.json()["id"]).reply_to_id, self.secret.id)

    def test_outsider_cannot_react(self):
        r = active_client(self.outsider).post(
            f"/api/conversations/messages/{self.secret.id}/react/", {"emoji": "👍"}, format="json")
        self.assertEqual(r.status_code, 403)
        self.assertFalse(self.secret.reactions.exists())

    def test_removed_creator_cannot_delete_the_thread(self):
        CommunityMembership.objects.filter(user=self.member, community=self.community).update(is_active=False)
        for url in (f"/api/conversations/{self.conv.id}/delete/", f"/api/conversations/{self.conv.id}/"):
            r = active_client(self.member).delete(url)
            self.assertEqual(r.status_code, 403, url)
        self.assertTrue(Conversation.objects.filter(id=self.conv.id).exists())

    def test_member_creator_can_still_delete_the_thread(self):
        r = active_client(self.member).delete(f"/api/conversations/{self.conv.id}/delete/")
        self.assertEqual(r.status_code, 204)
