from django.contrib.auth import get_user_model
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


class VerificationApiTests(TestCase):
    def setUp(self):
        from datetime import date
        from apps.users.models import KYCProfile, User
        self.applicant = User.objects.create(phone_number="254733000001", name="Ada L")
        self.kyc = KYCProfile.objects.create(
            user=self.applicant, given_names="Ada", surname="Lovelace", id_number="11223344",
            kra_pin="A012345678Z", date_of_birth=date(1990, 1, 1), status="pending",
            email="ada@example.com",
            verification_detail={"ocr": {"detected": True, "id_number_match": False, "mismatch": True}})

    def test_queue_requires_verification_view(self):
        # support has no verification.view
        self.assertEqual(op_client(make_staff("s@imbank.co.ke", "support"))
                         .get("/api/ops/verification/queue/").status_code, 403)

    def test_queue_lists_pending_with_flags(self):
        c = op_client(make_staff("v@imbank.co.ke", "verification"))
        body = c.get("/api/ops/verification/queue/").json()
        row = next(r for r in body["results"] if r["user_id"] == self.applicant.id)
        self.assertEqual(row["status"], "pending")
        self.assertTrue(row["ocr_mismatch"])
        self.assertIsNotNone(row["age_hours"])

    def test_case_detail(self):
        c = op_client(make_staff("v2@imbank.co.ke", "verification"))
        body = c.get(f"/api/ops/verification/{self.applicant.id}/").json()
        self.assertEqual(body["applicant"]["kra_pin"], "A012345678Z")
        self.assertIn("id_front", body["documents"])
        self.assertTrue(body["checks"]["ocr"]["mismatch"])

    def test_approve_decision_requires_decide_capability(self):
        # A verification *view*-only staffer can't decide (verification role has decide,
        # so use a role that views but not decides — auditor has verification.view only).
        auditor = make_staff("aud@imbank.co.ke", "auditor")
        r = op_client(auditor).post(f"/api/ops/verification/{self.applicant.id}/decision/",
                                    {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_approve_updates_status_and_audits(self):
        from apps.audit.models import AuditEvent
        from apps.users.models import KYCProfile
        c = op_client(make_staff("v3@imbank.co.ke", "verification"))
        r = c.post(f"/api/ops/verification/{self.applicant.id}/decision/",
                   {"action": "approve"}, format="json")
        self.assertEqual(r.status_code, 200, r.content)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, "approved")
        self.assertTrue(self.kyc.verification_provider.startswith("ops:"))
        self.assertTrue(AuditEvent.objects.filter(action="ops.verification.approve").exists())

    def test_reject_requires_reason(self):
        c = op_client(make_staff("v4@imbank.co.ke", "verification"))
        no_reason = c.post(f"/api/ops/verification/{self.applicant.id}/decision/",
                           {"action": "reject"}, format="json")
        self.assertEqual(no_reason.status_code, 400)
        ok = c.post(f"/api/ops/verification/{self.applicant.id}/decision/",
                    {"action": "reject", "reason": "Blurry ID"}, format="json")
        self.assertEqual(ok.status_code, 200)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.status, "rejected")
        self.assertEqual(self.kyc.rejection_reason, "Blurry ID")

    def test_request_resubmission_sets_items_no_status_change(self):
        c = op_client(make_staff("v5@imbank.co.ke", "verification"))
        r = c.post(f"/api/ops/verification/{self.applicant.id}/decision/",
                   {"action": "request_resubmission", "items": ["selfie", "bogus"]}, format="json")
        self.assertEqual(r.status_code, 200)
        self.kyc.refresh_from_db()
        self.assertEqual(self.kyc.resubmission_requested, ["selfie"])   # bogus filtered
        self.assertEqual(self.kyc.status, "pending")                    # unchanged


class OpsCommunitiesModuleTests(TestCase):
    """Communities ops module: registry, community file, suspend lever."""

    def setUp(self):
        from apps.communities.services import CommunityService
        owner = get_user_model().objects.create_user(phone_number="254700000091")
        self.community = CommunityService.create_community(
            owner, {"name": "Ops Test Chama", "is_private": False})
        self.manager = make_staff("comm-mgr@imbank.co.ke", "operations")
        self.viewer = make_staff("comm-view@imbank.co.ke", "analyst")

    def test_registry_lists_and_filters(self):
        res = op_client(self.manager).get("/api/ops/communities/", {"q": "Ops Test"})
        self.assertEqual(res.status_code, 200)
        row = res.data["results"][0]
        self.assertEqual(row["name"], "Ops Test Chama")
        self.assertEqual(row["status"], "active")
        self.assertEqual(row["member_count"], 1)

    def test_community_file_payload(self):
        res = op_client(self.viewer).get(f"/api/ops/communities/{self.community.id}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["members"]["admins"], 1)
        self.assertFalse(res.data["finance"]["has_financial_history"])
        self.assertIn("join_policy", res.data["settings"])

    def test_suspend_requires_reason_and_capability(self):
        url = f"/api/ops/communities/{self.community.id}/lifecycle/"
        # Analyst (view-only) cannot manage.
        res = op_client(self.viewer).post(url, {"action": "suspend", "reason": "x"}, format="json")
        self.assertEqual(res.status_code, 403)
        # Reason required.
        res = op_client(self.manager).post(url, {"action": "suspend"}, format="json")
        self.assertEqual(res.status_code, 400)
        # Suspend → status flips; audit rows on both trails.
        res = op_client(self.manager).post(url, {"action": "suspend", "reason": "fraud review"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "suspended")
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.community.suspend").exists())
        self.assertTrue(AuditEvent.objects.filter(action="community.suspended").exists())
        # Double-suspend → 409; unsuspend restores.
        res = op_client(self.manager).post(url, {"action": "suspend", "reason": "again"}, format="json")
        self.assertEqual(res.status_code, 409)
        res = op_client(self.manager).post(url, {"action": "unsuspend"}, format="json")
        self.assertEqual(res.data["status"], "active")


class OpsMetricsAndAuditTests(TestCase):

    def test_metrics_blocks_follow_capabilities(self):
        su = make_staff("metrics-su@imbank.co.ke", superuser=True)
        res = op_client(su).get("/api/ops/metrics/")
        self.assertEqual(res.status_code, 200)
        for block in ("verification", "holds", "outbox", "ledger", "communities", "users"):
            self.assertIn(block, res.data)
        self.assertTrue(res.data["ledger"]["balanced"])

        support = make_staff("metrics-sup@imbank.co.ke", "support")
        res = op_client(support).get("/api/ops/metrics/")
        self.assertEqual(res.status_code, 200)
        self.assertNotIn("ledger", res.data)   # support holds no ledger.view

    def test_audit_log_view_filters_and_requires_capability(self):
        from apps.audit.services import AuditService
        AuditService.log("ops.test.alpha", actor=None, target_type="thing", target_id="1")
        AuditService.log("community.suspended", actor=None, target_type="community", target_id="9")

        auditor = make_staff("aud@imbank.co.ke", "auditor")
        res = op_client(auditor).get("/api/ops/audit/", {"action": "community."})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["action"], "community.suspended")

        support = make_staff("sup2@imbank.co.ke", "support")
        self.assertEqual(op_client(support).get("/api/ops/audit/").status_code, 403)


class OpsUsersModuleTests(TestCase):
    """Users ops module: registry, User 360 (composed read), status lever
    through the domain service."""

    def setUp(self):
        from apps.communities.services import CommunityService
        self.member = get_user_model().objects.create_user(
            phone_number="254700000095", name="Akinyi O", is_phone_verified=True)
        self.community = CommunityService.create_community(
            self.member, {"name": "A360 Chama", "is_private": False})
        self.manager = make_staff("umgr@imbank.co.ke", "operations")
        self.viewer = make_staff("uview@imbank.co.ke", "auditor")

    def test_registry_search(self):
        res = op_client(self.viewer).get("/api/ops/users/", {"q": "Akinyi"})
        self.assertEqual(res.status_code, 200)
        row = res.data["results"][0]
        self.assertEqual(row["phone_number"], "254700000095")
        self.assertEqual(row["kyc_status"], "not_submitted")
        self.assertTrue(row["is_active"])

    def test_user_360_composed_blocks(self):
        res = op_client(self.viewer).get(f"/api/ops/users/{self.member.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["identity"]["phone_number"], "254700000095")
        self.assertEqual(res.data["verification"]["kyc_status"], "not_submitted")
        self.assertEqual(res.data["communities"][0]["name"], "A360 Chama")
        self.assertEqual(res.data["communities"][0]["role"], "admin")
        self.assertEqual(res.data["financial"]["total_position"], "0")
        self.assertEqual(res.data["financial"]["open_holds"], 0)
        self.assertIn("sessions", res.data)

    def test_staff_accounts_never_appear(self):
        staff_user = get_user_model().objects.create_user(
            phone_number="254700000096", is_staff=True)
        res = op_client(self.viewer).get("/api/ops/users/", {"q": "254700000096"})
        self.assertEqual(res.data["count"], 0)
        self.assertEqual(op_client(self.viewer).get(
            f"/api/ops/users/{staff_user.pk}/").status_code, 404)

    def test_status_lever_routes_through_domain_service(self):
        from apps.users.models import UserSession
        UserSession.objects.create(user=self.member, device_label="test phone")
        url = f"/api/ops/users/{self.member.pk}/status/"

        # Viewer lacks users.manage.
        self.assertEqual(op_client(self.viewer).post(
            url, {"action": "deactivate", "reason": "x"}, format="json").status_code, 403)
        # Reason required.
        self.assertEqual(op_client(self.manager).post(
            url, {"action": "deactivate"}, format="json").status_code, 400)

        res = op_client(self.manager).post(
            url, {"action": "deactivate", "reason": "fraud investigation"}, format="json")
        self.assertEqual(res.status_code, 200)
        self.member.refresh_from_db()
        self.assertFalse(self.member.is_active)
        # Sessions revoked by the domain service; both audit trails written.
        self.assertFalse(UserSession.objects.filter(
            user=self.member, revoked_at__isnull=True).exists())
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="user.deactivated").exists())
        self.assertTrue(AuditEvent.objects.filter(action="ops.user.deactivate").exists())

        # Double-deactivate → 409; reactivate restores.
        self.assertEqual(op_client(self.manager).post(
            url, {"action": "deactivate", "reason": "again"}, format="json").status_code, 409)
        res = op_client(self.manager).post(url, {"action": "reactivate"}, format="json")
        self.assertTrue(res.data["is_active"])


class OpsSupportModuleTests(TestCase):
    """Support desk: queue, raise through the domain service, resolve."""

    def setUp(self):
        self.member = get_user_model().objects.create_user(
            phone_number="254700000098", name="Baraka M")
        self.agent = make_staff("agent@imbank.co.ke", "support")
        self.auditor = make_staff("aud-sup@imbank.co.ke", "auditor")  # view-only

    def _raise(self, client, **over):
        body = {"phone_number": "254700000098", "kind": "address_proof",
                "title": "Proof of address needed",
                "detail": "Please upload a recent utility bill.", **over}
        return client.post("/api/ops/support/requests/", body, format="json")

    def test_raise_notifies_and_audits(self):
        from apps.core.models import OutboxEvent
        res = self._raise(op_client(self.agent))
        self.assertEqual(res.status_code, 201)
        self.assertEqual(res.data["status"], "open")
        # Durable notification event + both audit trails.
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="verification_request",
            payload__user_id=self.member.pk).exists())
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(
            action="user.verification_request_raised").exists())
        self.assertTrue(AuditEvent.objects.filter(
            action="ops.support.request_raised").exists())

    def test_raise_requires_act_capability_and_valid_member(self):
        self.assertEqual(self._raise(op_client(self.auditor)).status_code, 403)
        self.assertEqual(self._raise(op_client(self.agent),
                                     phone_number="254700099999").status_code, 404)
        self.assertEqual(self._raise(op_client(self.agent), kind="bogus").status_code, 400)

    def test_queue_and_resolve_flow(self):
        from apps.core.models import OutboxEvent
        rid = self._raise(op_client(self.agent)).data["id"]

        q = op_client(self.auditor).get("/api/ops/support/requests/", {"status": "open"})
        self.assertEqual(q.data["count"], 1)
        self.assertEqual(q.data["results"][0]["phone_number"], "254700000098")

        # View-only cannot resolve.
        self.assertEqual(op_client(self.auditor).post(
            f"/api/ops/support/requests/{rid}/resolve/", {}, format="json").status_code, 403)

        res = op_client(self.agent).post(
            f"/api/ops/support/requests/{rid}/resolve/",
            {"note": "Bill received — thanks."}, format="json")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "resolved")
        self.assertTrue(OutboxEvent.objects.filter(
            event_type="verification_request_resolved").exists())
        # Double resolve → 409; resolved leaves the open queue.
        self.assertEqual(op_client(self.agent).post(
            f"/api/ops/support/requests/{rid}/resolve/", {}, format="json").status_code, 409)
        q = op_client(self.agent).get("/api/ops/support/requests/", {"status": "open"})
        self.assertEqual(q.data["count"], 0)


class OpsTransactionsModuleTests(TestCase):
    """Transactions registry + Transaction 360, incl. the ledger.view-gated
    journal block backed by a real posted journal."""

    def setUp(self):
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger.posting_map import contribution_lines

        self.member = get_user_model().objects.create_user(
            phone_number="254700000099", name="Chebet K")
        self.ft = FinancialTransaction.objects.create(
            op_type="CONTRIBUTION", amount=Decimal("1500.00"),
            idempotency_key="ops-tx-test-1", initiated_by=self.member,
            mpesa_receipt="QA12ZZ99XY",
        )
        self.ft.transition_to("PROCESSING")
        self.ft.transition_to("SUCCESS")
        post_journal(
            idempotency_key="ops-tx-test-1-journal", op_type="CONTRIBUTION",
            lines=contribution_lines(member=self.member, fund_type="contribution",
                                     fund_id=999, gross=Money("1500.00")),
            narration="Test contribution", financial_transaction=self.ft,
        )
        self.finance = make_staff("fin@imbank.co.ke", "finance")      # +ledger.view
        self.support_agent = make_staff("sup-tx@imbank.co.ke", "support")  # tx.view only

    def test_registry_filters_and_state_mix(self):
        res = op_client(self.support_agent).get(
            "/api/ops/transactions/", {"q": "QA12ZZ99XY"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        row = res.data["results"][0]
        self.assertEqual(row["state"], "SUCCESS")
        self.assertEqual(row["amount"], "1500.00")
        self.assertEqual(row["initiated_by"], "Chebet K")
        self.assertEqual(res.data["by_state"].get("SUCCESS"), 1)

        none = op_client(self.support_agent).get(
            "/api/ops/transactions/", {"state": "FAILED"})
        self.assertEqual(none.data["count"], 0)

    def test_transaction_360_gates_journal_by_capability(self):
        url = f"/api/ops/transactions/{self.ft.pk}/"
        # transactions.view only → movement yes, journal absent.
        res = op_client(self.support_agent).get(url)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["movement"]["state"], "SUCCESS")
        self.assertEqual(res.data["rail"]["mpesa_receipt"], "QA12ZZ99XY")
        self.assertNotIn("journal", res.data)

        # finance holds ledger.view → balanced journal lines included.
        res = op_client(self.finance).get(url)
        self.assertIn("journal", res.data)
        lines = res.data["journal"][0]["lines"]
        self.assertGreaterEqual(len(lines), 2)
        from decimal import Decimal
        debits = sum(Decimal(l["amount"]) for l in lines if l["direction"] == "DEBIT")
        credits = sum(Decimal(l["amount"]) for l in lines if l["direction"] == "CREDIT")
        self.assertEqual(debits, credits)   # the 360 shows balanced truth

    def test_requires_transactions_view(self):
        dev = make_staff("dev-tx@imbank.co.ke", "developer")   # no transactions.view
        self.assertEqual(op_client(dev).get("/api/ops/transactions/").status_code, 403)
