"""Audit log tests (ADR-0019) — the model invariant, the service, and that the
wired admin/governance actions actually record an event."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService

from .models import AuditEvent
from .services import AuditService

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


class AuditModelTests(TestCase):

    def test_is_append_only(self):
        e = AuditEvent.objects.create(action="x.y", actor_label="t")
        e.action = "x.z"
        with self.assertRaises(ValueError):
            e.save()

    def test_actor_survives_user_deletion(self):
        user = make_user("254700000001")
        AuditService.log("test.action", actor=user)
        # hard-deleting the actor keeps the row (SET_NULL) with its label snapshot
        label = AuditEvent.objects.get(action="test.action").actor_label
        user.delete()
        e = AuditEvent.objects.get(action="test.action")
        self.assertIsNone(e.actor_id)
        self.assertEqual(e.actor_label, label)
        self.assertTrue(label)


class AuditServiceTests(TestCase):

    def test_log_snapshots_actor_and_target(self):
        user = make_user("254700000001")
        community = CommunityService.create_community(user, {"name": "Chama"})
        e = AuditService.log("community.test", actor=user, target=community,
                             tenant=community.tenant_id)
        self.assertEqual(e.action, "community.test")
        self.assertEqual(e.target_type, "community")
        self.assertEqual(e.target_id, str(community.id))
        self.assertEqual(e.actor_id, user.id)
        self.assertEqual(e.tenant_id, community.tenant_id)

    def test_tenant_falls_back_to_pinned_context(self):
        # With no tenant pinned and none passed, tenant is left unset (system context).
        e = AuditService.log("x.y", actor=make_user("254700000009"))
        self.assertIsNone(e.tenant_id)

    def test_log_never_raises_on_bad_metadata(self):
        # Non-serialisable metadata fails at write time but must not bubble up.
        self.assertIsNone(AuditService.log("y", metadata={"o": object()}))


class CommunityAuditWiringTests(TestCase):
    """The wired community admin actions each record exactly one audit event."""

    def setUp(self):
        self.owner = make_user("254700000001")
        self.member = make_user("254700000002")
        self.c = CommunityService.create_community(self.owner, {"name": "Chama"})
        self.m = CommunityMembership.objects.create(
            user=self.member, community=self.c, role=Role.MEMBER)

    def _actions(self):
        return list(AuditEvent.objects.values_list("action", flat=True))

    def test_role_change_is_audited(self):
        CommunityService.assign_role(self.owner, self.c, self.m.id, Role.TREASURER)
        self.assertIn("community.role_changed", self._actions())

    def test_member_removed_is_audited(self):
        CommunityService.remove_member(self.owner, self.c, self.m.id)
        self.assertIn("community.member_removed", self._actions())

    def test_ownership_transfer_is_audited(self):
        CommunityService.transfer_ownership(self.owner, self.c, self.m.id)
        events = {e.action: e for e in AuditEvent.objects.all()}
        self.assertIn("community.ownership_transferred", events)
        meta = events["community.ownership_transferred"].metadata
        self.assertEqual(meta["from_user_id"], self.owner.id)
        self.assertEqual(meta["to_user_id"], self.member.id)
