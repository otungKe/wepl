from django.contrib.auth.models import Group
from django.core.management import call_command
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from apps.backoffice.auth import issue_staff_token
from apps.backoffice.capabilities import (
    ALL_ROLES, capabilities_for, group_name, has_capability, is_operator, roles_for,
)
from apps.backoffice.models import StaffAccount


def make_staff(email, *roles, password="s3cret-pass!!", active=True, superuser=False,
               must_change=False):
    acct = StaffAccount.objects.create(
        email=email, full_name=email.split("@")[0], is_active=active,
        is_superuser=superuser, must_change_password=must_change,
    )
    acct.set_password(password)
    acct.save()
    for r in roles:
        g, _ = Group.objects.get_or_create(name=group_name(r))
        acct.groups.add(g)
    return acct


def op_client(staff):
    c = APIClient()
    c.credentials(HTTP_AUTHORIZATION=f"Bearer {issue_staff_token(staff)}")
    return c


class CapabilityMapTests(TestCase):
    def test_superuser_holds_all_capabilities(self):
        from apps.backoffice.capabilities import CAPABILITIES
        su = make_staff("root@imbank.co.ke", superuser=True)
        self.assertEqual(capabilities_for(su), set(CAPABILITIES))
        self.assertTrue(has_capability(su, "ledger.adjust"))

    def test_finance_role_capabilities(self):
        f = make_staff("fin@imbank.co.ke", "finance")
        self.assertEqual(roles_for(f), ["finance"])
        self.assertTrue(has_capability(f, "ledger.adjust"))
        self.assertFalse(has_capability(f, "verification.decide"))

    def test_support_is_read_oriented(self):
        s = make_staff("sup@imbank.co.ke", "support")
        self.assertTrue(has_capability(s, "users.view"))
        self.assertFalse(has_capability(s, "ledger.view"))

    def test_inactive_or_roleless_is_not_operator(self):
        self.assertFalse(is_operator(make_staff("x@imbank.co.ke", "finance", active=False)))
        self.assertFalse(is_operator(make_staff("y@imbank.co.ke")))  # no role


class StaffAuthTests(TestCase):
    def setUp(self):
        self.staff = make_staff("harry.onyango@imbank.co.ke", "finance", password="Correct-Horse-9")

    def test_login_success_returns_token(self):
        r = APIClient().post("/api/ops/auth/login/",
                             {"email": "harry.onyango@imbank.co.ke", "password": "Correct-Horse-9"},
                             format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.assertIn("token", r.json())
        self.assertFalse(r.json()["must_change_password"])

    def test_login_wrong_password_401(self):
        r = APIClient().post("/api/ops/auth/login/",
                             {"email": "harry.onyango@imbank.co.ke", "password": "nope"}, format="json")
        self.assertEqual(r.status_code, 401)

    def test_inactive_account_cannot_login(self):
        self.staff.is_active = False; self.staff.save()
        r = APIClient().post("/api/ops/auth/login/",
                             {"email": "harry.onyango@imbank.co.ke", "password": "Correct-Horse-9"},
                             format="json")
        self.assertEqual(r.status_code, 401)

    def test_token_authenticates_me_endpoint(self):
        r = op_client(self.staff).get("/api/ops/me/")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["email"], "harry.onyango@imbank.co.ke")
        self.assertIn("ledger.adjust", r.json()["capabilities"])

    def test_no_token_is_401(self):
        self.assertEqual(APIClient().get("/api/ops/me/").status_code, 401)

    def test_change_password_requires_current(self):
        c = op_client(self.staff)
        bad = c.post("/api/ops/auth/change-password/",
                     {"current_password": "wrong", "new_password": "Brand-New-Pass-1"}, format="json")
        self.assertEqual(bad.status_code, 400)
        ok = c.post("/api/ops/auth/change-password/",
                    {"current_password": "Correct-Horse-9", "new_password": "Brand-New-Pass-1"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.must_change_password)
        self.assertTrue(self.staff.check_password("Brand-New-Pass-1"))

    def test_first_login_flags_password_change(self):
        acct = make_staff("new.op@imbank.co.ke", "support", must_change=True)
        r = APIClient().post("/api/ops/auth/login/",
                             {"email": "new.op@imbank.co.ke", "password": "s3cret-pass!!"}, format="json")
        self.assertTrue(r.json()["must_change_password"])

    def test_admin_reset_forces_change_and_no_self_service(self):
        temp = self.staff.force_reset()
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.must_change_password)
        self.assertTrue(self.staff.check_password(temp))
        # There is no self-service reset endpoint.
        self.assertEqual(APIClient().post("/api/ops/auth/reset/", {}, format="json").status_code, 404)


class OpsMeEndpointTests(TestCase):
    def test_roleless_staff_forbidden(self):
        self.assertEqual(op_client(make_staff("nobody@imbank.co.ke")).get("/api/ops/me/").status_code, 403)

    def test_operator_gets_roles(self):
        body = op_client(make_staff("v@imbank.co.ke", "verification")).get("/api/ops/me/").json()
        self.assertEqual(body["roles"], ["verification"])
        self.assertIn("verification.decide", body["capabilities"])


class OpsSearchTests(TestCase):
    def setUp(self):
        from datetime import date
        from apps.communities.services import CommunityService
        from apps.users.models import KYCProfile, User
        self.target = User.objects.create(phone_number="254712345678", name="Ada Lovelace")
        KYCProfile.objects.create(user=self.target, given_names="Ada", surname="Lovelace",
            id_number="87654321", date_of_birth=date(1990, 1, 1), status="pending")
        creator = User.objects.create(phone_number="254700000099")
        CommunityService.create_community(creator, {"name": "Riverside Chama"})

    def test_capability_scoped(self):
        support = op_client(make_staff("s2@imbank.co.ke", "support"))
        fin = op_client(make_staff("f2@imbank.co.ke", "finance"))
        self.assertNotIn("journal", support.get("/api/ops/search/?q=CONTRIB").json()["counts"])
        self.assertIn("journal", fin.get("/api/ops/search/?q=CONTRIB").json()["counts"])

    def test_user_lookup_and_audit(self):
        from apps.audit.models import AuditEvent
        op_client(make_staff("s3@imbank.co.ke", "support")).get("/api/ops/search/?q=Ada")
        self.assertTrue(AuditEvent.objects.filter(action="ops.search.performed").exists())


class OpsAuditTests(TestCase):
    def test_staff_action_attributed_by_email(self):
        from apps.audit.models import AuditEvent
        from apps.backoffice.audit import record_action
        staff = make_staff("auditee@imbank.co.ke", "finance")
        record_action(action="ops.test.performed", actor=staff, metadata={"k": "v"})
        ev = AuditEvent.objects.get(action="ops.test.performed")
        self.assertIsNone(ev.actor_id)                     # not the customer FK
        self.assertEqual(ev.actor_label, "auditee@imbank.co.ke")
        self.assertEqual(ev.metadata["staff_id"], staff.id)


class BootstrapTests(TestCase):
    def test_seed_ops_roles(self):
        call_command("seed_ops_roles")
        for role in ALL_ROLES:
            self.assertTrue(Group.objects.filter(name=group_name(role)).exists(), role)

    @override_settings()
    def test_create_ops_admin_from_env(self):
        import os
        os.environ["OPS_ADMIN_EMAIL"] = "boss@imbank.co.ke"
        os.environ["OPS_ADMIN_PASSWORD"] = "Bootstrap-Pass-1"
        try:
            call_command("create_ops_admin")
        finally:
            del os.environ["OPS_ADMIN_EMAIL"]; del os.environ["OPS_ADMIN_PASSWORD"]
        acct = StaffAccount.objects.get(email="boss@imbank.co.ke")
        self.assertTrue(acct.is_superuser)
        self.assertFalse(acct.must_change_password)
        self.assertTrue(acct.check_password("Bootstrap-Pass-1"))
