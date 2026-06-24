"""Chat scaling tests (ADR-0012): read high-water-mark, cheap unread, keyset pagination."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

from .models import Conversation, Message
from .services import ConversationService

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


def active_client(user):
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    c = APIClient()
    c.force_authenticate(user=user, token=token)
    return c


class UnreadHighWaterMarkTests(TestCase):

    def setUp(self):
        self.owner = make_user("254700000001")
        self.member = make_user("254700000002")
        self.community = CommunityService.create_community(self.owner, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.member, community=self.community, role=Role.MEMBER)
        self.conv = Conversation.objects.create(
            community=self.community, topic="General", created_by=self.owner)

    def _msg(self, sender, body):
        return Message.objects.create(conversation=self.conv, sender=sender, content=body)

    def test_unread_counts_others_messages(self):
        self._msg(self.owner, "a")
        self._msg(self.owner, "b")
        summary = ConversationService.get_unread_summary(self.member)
        self.assertEqual(summary["total"], 2)
        self.assertEqual(summary["by_community"][str(self.community.id)], 2)

    def test_own_messages_not_counted(self):
        self._msg(self.member, "mine")
        self.assertEqual(ConversationService.get_unread_summary(self.member)["total"], 0)

    def test_mark_read_clears_unread_via_high_water_mark(self):
        self._msg(self.owner, "a")
        self._msg(self.owner, "b")
        ConversationService.mark_read(self.conv.id, self.member)
        rs = self.conv.read_statuses.get(user=self.member)
        self.assertIsNotNone(rs.last_read_message_id)
        self.assertEqual(ConversationService.get_unread_summary(self.member)["total"], 0)
        # a new message after read is unread again
        self._msg(self.owner, "c")
        self.assertEqual(ConversationService.get_unread_summary(self.member)["total"], 1)

    def test_deleted_messages_not_counted(self):
        m = self._msg(self.owner, "x")
        m.is_deleted = True
        m.save(update_fields=["is_deleted"])
        self.assertEqual(ConversationService.get_unread_summary(self.member)["total"], 0)


class MessageKeysetPaginationTests(TestCase):

    def setUp(self):
        self.user = make_user("254700000001")
        self.community = CommunityService.create_community(self.user, {"name": "Chama"})
        self.conv = Conversation.objects.create(
            community=self.community, topic="General", created_by=self.user)
        self.ids = [
            Message.objects.create(conversation=self.conv, sender=self.user, content=str(i)).id
            for i in range(120)
        ]

    def test_default_limit_returns_recent_50_ascending(self):
        r = active_client(self.user).get(f"/api/conversations/{self.conv.id}/messages/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body), 50)                 # bounded, not all 120
        returned = [m["id"] for m in body]
        self.assertEqual(returned, sorted(returned))    # ascending
        self.assertEqual(returned[-1], self.ids[-1])    # newest included

    def test_limit_param_capped(self):
        r = active_client(self.user).get(
            f"/api/conversations/{self.conv.id}/messages/?limit=999")
        self.assertEqual(len(r.json()), 120)            # capped at MAX_LIMIT(200) → all 120

    def test_before_cursor_fetches_older_page(self):
        # page 1: most recent 50
        first = [m["id"] for m in active_client(self.user).get(
            f"/api/conversations/{self.conv.id}/messages/?limit=50").json()]
        oldest_seen = first[0]
        # page 2: older than the oldest seen
        older = [m["id"] for m in active_client(self.user).get(
            f"/api/conversations/{self.conv.id}/messages/?limit=50&before={oldest_seen}").json()]
        self.assertTrue(older)
        self.assertTrue(max(older) < oldest_seen)       # strictly older, no overlap
        self.assertEqual(older, sorted(older))
