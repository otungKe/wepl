from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase
from rest_framework.test import APIClient

from apps.backoffice.capabilities import (
    ALL_ROLES, capabilities_for, group_name, has_capability, is_operator, roles_for,
)

User = get_user_model()


def make_operator(phone, *roles, staff=True, superuser=False):
    u = User.objects.create(phone_number=phone, is_staff=staff, is_superuser=superuser)
    for r in roles:
        g, _ = Group.objects.get_or_create(name=group_name(r))
        u.groups.add(g)
    return u


class CapabilityMapTests(TestCase):
    def test_superuser_holds_all_capabilities(self):
        su = make_operator("254700000001", superuser=True)
        from apps.backoffice.capabilities import CAPABILITIES
        self.assertEqual(capabilities_for(su), set(CAPABILITIES))
        self.assertTrue(has_capability(su, "ledger.adjust"))

    def test_finance_role_capabilities(self):
        f = make_operator("254700000002", "finance")
        self.assertEqual(roles_for(f), ["finance"])
        self.assertTrue(has_capability(f, "ledger.adjust"))
        self.assertTrue(has_capability(f, "finops.approve"))
        # Finance is not a verification officer.
        self.assertFalse(has_capability(f, "verification.decide"))

    def test_support_is_read_oriented(self):
        s = make_operator("254700000003", "support")
        self.assertTrue(has_capability(s, "users.view"))
        self.assertFalse(has_capability(s, "ledger.view"))
        self.assertFalse(has_capability(s, "config.change"))

    def test_non_staff_has_nothing(self):
        u = make_operator("254700000004", "finance", staff=False)
        self.assertFalse(has_capability(u, "ledger.view"))
        self.assertFalse(is_operator(u))

    def test_multiple_roles_union(self):
        u = make_operator("254700000005", "risk", "verification")
        self.assertTrue(has_capability(u, "risk.decide"))
        self.assertTrue(has_capability(u, "verification.decide"))


class OpsMeEndpointTests(TestCase):
    def _client(self, user):
        c = APIClient()
        c.force_authenticate(user=user)
        return c

    def test_plain_user_is_forbidden(self):
        u = make_operator("254700000010", staff=False)
        self.assertEqual(self._client(u).get("/api/ops/me/").status_code, 403)

    def test_staff_without_role_is_forbidden(self):
        u = make_operator("254700000011")  # staff but no ops group
        self.assertEqual(self._client(u).get("/api/ops/me/").status_code, 403)

    def test_operator_gets_roles_and_capabilities(self):
        u = make_operator("254700000012", "finance")
        r = self._client(u).get("/api/ops/me/")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(body["roles"], ["finance"])
        self.assertIn("ledger.adjust", body["capabilities"])
        self.assertNotIn("verification.decide", body["capabilities"])

    def test_superuser_sees_everything(self):
        su = make_operator("254700000013", superuser=True)
        body = self._client(su).get("/api/ops/me/").json()
        self.assertIn("config.change", body["capabilities"])
        self.assertTrue(body["is_superuser"])


class OpsAuditTests(TestCase):
    def test_record_action_writes_audit_event(self):
        from apps.audit.models import AuditEvent
        from apps.backoffice.audit import record_action
        actor = make_operator("254700000020", "finance")
        record_action(action="ops.test.performed", actor=actor,
                      target_type="KYCProfile", target_id="42", metadata={"k": "v"})
        ev = AuditEvent.objects.get(action="ops.test.performed")
        self.assertEqual(ev.actor_id, actor.id)
        self.assertEqual(ev.target_id, "42")
        self.assertEqual(ev.metadata, {"k": "v"})

    def test_record_action_never_raises(self):
        from apps.backoffice.audit import record_action
        # Bad metadata type shouldn't bubble up and break the caller's action.
        record_action(action="ops.test.safe", actor=None, metadata=None)


class SeedOpsRolesTests(TestCase):
    def test_seeds_all_role_groups(self):
        call_command("seed_ops_roles")
        for role in ALL_ROLES:
            self.assertTrue(Group.objects.filter(name=group_name(role)).exists(), role)
