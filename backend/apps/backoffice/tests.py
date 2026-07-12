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


def stepped_up(staff):
    """Extra request kwargs carrying a valid step-up elevation token, as the
    console attaches after an operator passes step-up (see stepup.py, OP-3)."""
    from apps.backoffice.stepup import issue_stepup_token
    return {"HTTP_X_OPS_STEPUP": issue_stepup_token(staff)}


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
        step = stepped_up(self.manager)
        # Analyst (view-only) cannot manage.
        res = op_client(self.viewer).post(url, {"action": "suspend", "reason": "x"}, format="json")
        self.assertEqual(res.status_code, 403)
        # Manager has the capability but no step-up → still refused.
        res = op_client(self.manager).post(url, {"action": "suspend", "reason": "x"}, format="json")
        self.assertEqual(res.status_code, 403)
        # Reason required (with step-up present so it reaches the view).
        res = op_client(self.manager).post(url, {"action": "suspend"}, format="json", **step)
        self.assertEqual(res.status_code, 400)
        # Suspend → status flips; audit rows on both trails.
        res = op_client(self.manager).post(url, {"action": "suspend", "reason": "fraud review"}, format="json", **step)
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["status"], "suspended")
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.community.suspend").exists())
        self.assertTrue(AuditEvent.objects.filter(action="community.suspended").exists())
        # Double-suspend → 409; unsuspend restores.
        res = op_client(self.manager).post(url, {"action": "suspend", "reason": "again"}, format="json", **step)
        self.assertEqual(res.status_code, 409)
        res = op_client(self.manager).post(url, {"action": "unsuspend"}, format="json", **step)
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

    def test_user_360_with_contribution_does_not_error(self):
        # Regression: a member with an active contribution must not 500 the 360.
        # The financial block read Contribution.name, which doesn't exist (it's
        # .title) — so any funded member's 360 failed to load.
        from apps.contributions.services import ContributionService
        ContributionService.create_contribution(self.member, {"title": "Harambee Pool"})
        res = op_client(self.viewer).get(f"/api/ops/users/{self.member.pk}/")
        self.assertEqual(res.status_code, 200)
        positions = res.data["financial"]["positions"]
        self.assertTrue(any(p["name"] == "Harambee Pool" for p in positions))
        # A 360 read must not have minted a sub-ledger account as a side effect.
        from apps.ledger.models import Account
        self.assertFalse(Account.objects.filter(owner=self.member).exists())

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
        step = stepped_up(self.manager)

        # Viewer lacks users.manage.
        self.assertEqual(op_client(self.viewer).post(
            url, {"action": "deactivate", "reason": "x"}, format="json").status_code, 403)
        # Manager has the capability but no step-up → still refused.
        self.assertEqual(op_client(self.manager).post(
            url, {"action": "deactivate", "reason": "x"}, format="json").status_code, 403)
        # Reason required (with step-up present).
        self.assertEqual(op_client(self.manager).post(
            url, {"action": "deactivate"}, format="json", **step).status_code, 400)

        res = op_client(self.manager).post(
            url, {"action": "deactivate", "reason": "fraud investigation"}, format="json", **step)
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
            url, {"action": "deactivate", "reason": "again"}, format="json", **step).status_code, 409)
        res = op_client(self.manager).post(url, {"action": "reactivate"}, format="json", **step)
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

    def test_registry_is_inquiry_first(self):
        c = op_client(self.support_agent)
        # No criteria → nothing listed, just a prompt (and the op-type choices).
        idle = c.get("/api/ops/transactions/")
        self.assertEqual(idle.status_code, 200)
        self.assertTrue(idle.data["prompt"])
        self.assertEqual(idle.data["results"], [])
        self.assertTrue(idle.data["op_types"])   # dropdown still populated
        # state='all' alone is not a query either.
        self.assertTrue(c.get("/api/ops/transactions/", {"state": "all"}).data["prompt"])

    def test_registry_returns_matches_once_a_criterion_is_given(self):
        res = op_client(self.support_agent).get(
            "/api/ops/transactions/", {"q": "QA12ZZ99XY"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["prompt"])
        self.assertEqual(res.data["count"], 1)
        row = res.data["results"][0]
        self.assertEqual(row["state"], "SUCCESS")
        self.assertEqual(row["amount"], "1500.00")
        self.assertEqual(row["initiated_by"], "Chebet K")
        # An explicit state is a valid criterion; FAILED matches nothing here.
        none = op_client(self.support_agent).get(
            "/api/ops/transactions/", {"state": "FAILED"})
        self.assertFalse(none.data["prompt"])
        self.assertEqual(none.data["count"], 0)

    def test_transaction_360_shows_debits_and_credits_to_any_viewer(self):
        from decimal import Decimal
        url = f"/api/ops/transactions/{self.ft.pk}/"
        # Every transaction viewer sees which accounts were debited/credited —
        # a movement without its double-entry is only half the story.
        for staff in (self.support_agent, self.finance):
            res = op_client(staff).get(url)
            self.assertEqual(res.status_code, 200)
            self.assertIn("journal", res.data)
            lines = res.data["journal"][0]["lines"]
            self.assertGreaterEqual(len(lines), 2)
            debits = sum(Decimal(l["amount"]) for l in lines if l["direction"] == "DEBIT")
            credits = sum(Decimal(l["amount"]) for l in lines if l["direction"] == "CREDIT")
            self.assertEqual(debits, credits)   # balanced truth
            # Each line names the account it touched.
            self.assertTrue(all(l["account_code"] and l["account_name"] for l in lines))

    def test_requires_transactions_view(self):
        dev = make_staff("dev-tx@imbank.co.ke", "developer")   # no transactions.view
        self.assertEqual(op_client(dev).get("/api/ops/transactions/").status_code, 403)

    def test_counterparty_name_shown_in_full_to_ops(self):
        # A payout whose recipient M-Pesa name was captured from the B2C callback.
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        ft = FinancialTransaction.objects.create(
            op_type="DISBURSEMENT", amount=Decimal("2000.00"),
            idempotency_key="cp-name-1", initiated_by=self.member,
            recipient_phone="254712345678", counterparty_name="JOHN DOE",
            mpesa_receipt="CPNAME01")
        c = op_client(self.support_agent)
        # Registry row carries it.
        row = c.get("/api/ops/transactions/", {"q": "CPNAME01"}).data["results"][0]
        self.assertEqual(row["counterparty_name"], "JOHN DOE")
        # Transaction 360 parties block shows it, and the phone is unmasked for ops.
        d = c.get(f"/api/ops/transactions/{ft.pk}/").data
        self.assertEqual(d["parties"]["counterparty_name"], "JOHN DOE")
        self.assertEqual(d["parties"]["recipient_phone"], "254712345678")

    def test_pool_linked_transaction_renders_in_registry_and_360(self):
        # Regression: a transaction tied to a contribution pool must not 500 the
        # registry or the 360. _fund_of read Contribution.name — the field is
        # .title — so any funded movement (e.g. a real deposit) broke the screen.
        from decimal import Decimal
        from apps.contributions.services import ContributionService
        from apps.ledger.models import FinancialTransaction
        pool = ContributionService.create_contribution(self.member, {"title": "Test Pool"})
        ft = FinancialTransaction.objects.create(
            op_type="CONTRIBUTION", amount=Decimal("10.00"), idempotency_key="pool-linked-1",
            initiated_by=self.member, contribution=pool, mpesa_receipt="POOLRCPT1")

        res = op_client(self.support_agent).get("/api/ops/transactions/", {"q": "POOLRCPT1"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"][0]["fund"], "Pool · Test Pool")

        res = op_client(self.support_agent).get(f"/api/ops/transactions/{ft.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["context"]["fund"], "Pool · Test Pool")

    def test_registry_filters_by_account_amount_and_date(self):
        from datetime import timedelta
        from django.utils import timezone
        base = "/api/ops/transactions/"
        c = op_client(self.support_agent)   # self.ft: 1500, journal touches float 1000

        # By ledger account touched — the M-Pesa float (code 1000).
        res = c.get(base, {"account": "1000"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(any(r["id"] == self.ft.pk for r in res.data["results"]))
        # An account the movement never touched returns nothing.
        self.assertEqual(c.get(base, {"account": "SL-NOPE-0-U0"}).data["count"], 0)

        # Amount range.
        self.assertFalse(any(r["id"] == self.ft.pk
                             for r in c.get(base, {"max": "1000"}).data["results"]))
        self.assertTrue(any(r["id"] == self.ft.pk
                            for r in c.get(base, {"min": "1000"}).data["results"]))

        # Date range — tomorrow onward excludes today's movement. Use localdate():
        # the filter interprets the date string as a settings-timezone (local)
        # midnight, so a UTC-based date is off by one between 21:00–24:00 UTC.
        tomorrow = (timezone.localdate() + timedelta(days=1)).isoformat()
        self.assertEqual(c.get(base, {"date_from": tomorrow}).data["count"], 0)
        today = timezone.localdate().isoformat()
        self.assertTrue(any(r["id"] == self.ft.pk
                            for r in c.get(base, {"date_from": today}).data["results"]))

    def test_registry_filters_by_fund(self):
        from decimal import Decimal
        from apps.contributions.services import ContributionService
        from apps.ledger.models import FinancialTransaction
        pool = ContributionService.create_contribution(self.member, {"title": "Filter Pool"})
        ft = FinancialTransaction.objects.create(
            op_type="CONTRIBUTION", amount=Decimal("20.00"), idempotency_key="fund-filter-1",
            initiated_by=self.member, contribution=pool)
        res = op_client(self.support_agent).get(
            "/api/ops/transactions/", {"fund_type": "contribution", "fund_id": pool.id})
        self.assertEqual(res.status_code, 200)
        ids = [r["id"] for r in res.data["results"]]
        self.assertIn(ft.pk, ids)
        self.assertNotIn(self.ft.pk, ids)   # different pool / no fund FK


class OpsAccountsModuleTests(TestCase):
    """Chart-of-Accounts browser (/api/ops/accounts/) — the ADR-0025 account
    search surface: inquiry-first, structured filters over the whole tree
    (GL heads, pool control accounts, member sub-ledgers), ledger.view-gated."""

    def setUp(self):
        from apps.ledger import coa
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger.posting_map import contribution_lines

        coa.seed_chart_of_accounts()
        self.member = get_user_model().objects.create_user(
            phone_number="254700000201", name="Amina W", member_number="WM-0000201")
        # A real contribution posting mints the pool + member sub-ledger and
        # gives them a non-zero balance.
        post_journal(
            idempotency_key="acct-search-seed-1", op_type="CONTRIBUTION",
            lines=contribution_lines(member=self.member, fund_type="contribution",
                                     fund_id=42, gross=Money("500.00")),
            narration="Seed", financial_transaction=None,
        )
        self.finance = make_staff("acct-fin@imbank.co.ke", "finance")   # +ledger.view
        self.support = make_staff("acct-sup@imbank.co.ke", "support")   # no ledger.view

    def test_requires_ledger_view(self):
        # A support agent (transactions.view but not ledger.view) is refused.
        self.assertEqual(
            op_client(self.support).get("/api/ops/accounts/").status_code, 403)

    def test_browser_is_inquiry_first(self):
        c = op_client(self.finance)
        idle = c.get("/api/ops/accounts/")
        self.assertEqual(idle.status_code, 200)
        self.assertTrue(idle.data["prompt"])
        self.assertEqual(idle.data["results"], [])
        # Static facets ride along so the form can populate without a query.
        self.assertTrue(idle.data["facets"]["types"])
        self.assertTrue(idle.data["facets"]["gl_heads"])

    def test_search_by_code_returns_the_gl_head(self):
        res = op_client(self.finance).get("/api/ops/accounts/", {"q": "2000"})
        self.assertEqual(res.status_code, 200)
        self.assertFalse(res.data["prompt"])
        codes = {r["code"]: r for r in res.data["results"]}
        self.assertIn("2000", codes)
        self.assertEqual(codes["2000"]["role"], "gl")
        # Every row carries its external handle.
        self.assertTrue(all(r["account_uid"] for r in res.data["results"]))

    def test_search_by_member_owner(self):
        # By member number — only that member's sub-ledgers.
        res = op_client(self.finance).get(
            "/api/ops/accounts/", {"owner": "WM-0000201"})
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.data["count"] >= 1)
        self.assertTrue(all(r["role"] == "member" for r in res.data["results"]))
        row = res.data["results"][0]
        self.assertEqual(row["owner_member_no"], "WM-0000201")
        from decimal import Decimal
        self.assertEqual(Decimal(row["balance"]), Decimal("500"))  # credit-normal liability
        # An unresolvable member handle returns nothing, not the whole book.
        empty = op_client(self.finance).get("/api/ops/accounts/", {"owner": "ZZ-NOBODY"})
        self.assertEqual(empty.data["count"], 0)

    def test_search_by_fund_returns_pool_and_members_under_gl(self):
        c = op_client(self.finance)
        res = c.get("/api/ops/accounts/",
                    {"fund_type": "contribution", "fund_id": 42})
        self.assertEqual(res.status_code, 200)
        roles = {r["role"] for r in res.data["results"]}
        self.assertIn("pool", roles)      # the fund control account
        self.assertIn("member", roles)    # its member sub-ledger
        # The GL-head facet narrows to that subtree too.
        gl = c.get("/api/ops/accounts/", {"gl": "2000", "role": "member"})
        self.assertTrue(all(r["role"] == "member" for r in gl.data["results"]))

    def test_account_360_shows_tree_context(self):
        from apps.ledger.coa import pool_account
        pool = pool_account(fund_type="contribution", fund_id=42)
        res = op_client(self.finance).get(f"/api/ops/accounts/{pool.pk}/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["role"], "pool")
        self.assertEqual(res.data["parent"]["code"], "2000")   # rolls into the GL
        self.assertTrue(res.data["children"])                  # its members
        self.assertGreaterEqual(res.data["child_count"], 1)


class StepUpTOTPTests(TestCase):
    """OP-3 step-up: TOTP enrolment, elevation, recovery codes, and the
    RequireStepUp gate on destructive levers."""

    def setUp(self):
        self.staff = make_staff("stepup@imbank.co.ke", "operations")

    def _current_code(self, secret):
        import pyotp
        return pyotp.TOTP(secret).now()

    def test_enroll_confirm_and_step_up_flow(self):
        c = op_client(self.staff)
        # /me/ reflects not-yet-enrolled.
        self.assertFalse(c.get("/api/ops/me/").data["totp_enrolled"])

        setup = c.post("/api/ops/auth/totp/setup/", {}, format="json")
        self.assertEqual(setup.status_code, 200)
        secret = setup.data["secret"]
        self.assertTrue(setup.data["provisioning_uri"].startswith("otpauth://totp/"))

        # A wrong code cannot confirm enrolment.
        self.assertEqual(c.post("/api/ops/auth/totp/confirm/",
                                {"code": "000000"}, format="json").status_code, 400)

        confirm = c.post("/api/ops/auth/totp/confirm/",
                         {"code": self._current_code(secret)}, format="json")
        self.assertEqual(confirm.status_code, 200)
        self.assertEqual(len(confirm.data["recovery_codes"]), 10)
        self.staff.refresh_from_db()
        self.assertTrue(self.staff.totp_enrolled)
        self.assertTrue(c.get("/api/ops/me/").data["totp_enrolled"])

        # Step-up with a live code returns an elevation token.
        step = c.post("/api/ops/auth/step-up/",
                      {"code": self._current_code(secret)}, format="json")
        self.assertEqual(step.status_code, 200)
        self.assertTrue(step.data["token"])
        self.assertEqual(step.data["expires_in"], 300)

    def test_step_up_requires_enrolment_and_rejects_bad_codes(self):
        c = op_client(self.staff)
        # Not enrolled → 409 with a machine-readable code.
        res = c.post("/api/ops/auth/step-up/", {"code": "123456"}, format="json")
        self.assertEqual(res.status_code, 409)
        self.assertEqual(res.data["code"], "not_enrolled")

        self.staff.begin_totp_enrollment()
        self.staff.confirm_totp_enrollment(self._current_code(self.staff.totp_secret))
        # Enrolled, but a wrong code is refused.
        self.assertEqual(c.post("/api/ops/auth/step-up/",
                                {"code": "000000"}, format="json").status_code, 400)

    def test_recovery_code_is_single_use(self):
        self.staff.begin_totp_enrollment()
        codes = self.staff.confirm_totp_enrollment(self._current_code(self.staff.totp_secret))
        recovery = codes[0]
        # First use works; the same code cannot be replayed.
        self.assertTrue(self.staff.verify_stepup(recovery))
        self.staff.refresh_from_db()
        self.assertFalse(self.staff.verify_stepup(recovery))
        self.assertEqual(len(self.staff.totp_recovery_codes), 9)

    def test_totp_secret_is_encrypted_at_rest(self):
        from django.db import connection
        self.staff.begin_totp_enrollment()
        secret = self.staff.totp_secret
        self.staff.confirm_totp_enrollment(self._current_code(secret))
        self.assertTrue(secret)
        table = StaffAccount._meta.db_table
        with connection.cursor() as cur:
            cur.execute(f"SELECT totp_secret FROM {table} WHERE id = %s", [self.staff.id])
            raw = cur.fetchone()[0]
        # Stored ciphertext must not be (or contain) the plaintext seed.
        self.assertNotEqual(raw, secret)
        self.assertNotIn(secret, raw)
        # The ORM decrypts transparently on reload, so the seed still works.
        fresh = StaffAccount.objects.get(pk=self.staff.pk)
        self.assertEqual(fresh.totp_secret, secret)
        self.assertTrue(fresh.verify_stepup(self._current_code(secret)))

    def test_gate_rejects_foreign_and_expired_tokens(self):
        from apps.backoffice.stepup import issue_stepup_token
        other = make_staff("other-stepup@imbank.co.ke", "operations")
        member = get_user_model().objects.create_user(phone_number="254700000077")
        url = f"/api/ops/users/{member.pk}/status/"
        # A step-up token minted for a *different* operator must not elevate me.
        foreign = {"HTTP_X_OPS_STEPUP": issue_stepup_token(other)}
        res = op_client(self.staff).post(
            url, {"action": "deactivate", "reason": "x"}, format="json", **foreign)
        self.assertEqual(res.status_code, 403)


class _StubProvider:
    """A provider whose query_status returns a fixed state (test control)."""
    name = "fake"

    def __init__(self, state):
        self._state = state

    def query_status(self, *, provider_ref):
        from apps.payments.providers import StatusResult
        return StatusResult(state=self._state, raw={"provider_ref": provider_ref})


class FinopsModuleTests(TestCase):
    """OP-1 FinOps levers: requery / mark_failed heal a stuck payout through the
    pipeline, keep the ledger balanced, and are capability + step-up gated."""

    def setUp(self):
        from apps.payments.providers import registry
        self.addCleanup(registry.use_provider, None)
        self.member = get_user_model().objects.create_user(
            phone_number="254700000201", name="Wanjiru M")
        self.finance = make_staff("finops@imbank.co.ke", "finance")   # +finops.retry/.view
        self.viewer = make_staff("finops-view@imbank.co.ke", "auditor")

    def _stuck_payout(self, key="op1-payout-1", conv="AG_CONV_1"):
        """A DISBURSEMENT FT in PROCESSING with a reserved-funds journal posted."""
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger.posting_map import disbursement_lines
        ft = FinancialTransaction.objects.create(
            op_type="DISBURSEMENT", amount=Decimal("2000.00"), idempotency_key=key,
            initiated_by=self.member, recipient_phone="254700000201",
            mpesa_conversation_id=conv,
        )
        ft.transition_to("PROCESSING")
        post_journal(
            idempotency_key=f"{key}-journal", op_type="DISBURSEMENT",
            lines=disbursement_lines(member=self.member, fund_type="contribution",
                                     fund_id=555, amount=Money("2000.00")),
            narration="Test disbursement", financial_transaction=ft,
        )
        return ft

    def _stepup(self):
        return stepped_up(self.finance)

    def test_requery_heals_success_through_pipeline(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("success"))
        ft = self._stuck_payout()
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "requery"}, format="json", **self._stepup())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"]["outcome"], "healed_success")
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.finops.requery").exists())

    def test_requery_failure_reverses_and_keeps_ledger_balanced(self):
        from apps.payments.providers import registry
        from apps.ledger.balances import trial_balance
        registry.use_provider(_StubProvider("failed"))
        ft = self._stuck_payout(key="op1-payout-2", conv="AG_CONV_2")
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "requery"}, format="json", **self._stepup())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"]["outcome"], "healed_failed")
        ft.refresh_from_db()
        self.assertEqual(ft.state, "FAILED")
        # Reserved funds restored: the reversal keeps the trial balance at zero.
        self.assertTrue(trial_balance()["balanced"])

    def test_requery_pending_is_a_noop(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("pending"))
        ft = self._stuck_payout(key="op1-payout-3", conv="AG_CONV_3")
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "requery"}, format="json", **self._stepup())
        self.assertEqual(res.data["result"]["outcome"], "pending")
        ft.refresh_from_db()
        self.assertEqual(ft.state, "PROCESSING")

    def test_mark_failed_refuses_when_rail_says_success(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("success"))
        ft = self._stuck_payout(key="op1-payout-4", conv="AG_CONV_4")
        # Operator wants to fail it, but the rail confirms it actually succeeded →
        # it is healed as success, never stranded.
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "mark_failed", "reason": "looks stuck"}, format="json", **self._stepup())
        self.assertEqual(res.data["result"]["outcome"], "healed_success")
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")

    def test_mark_failed_requires_reason(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("pending"))
        ft = self._stuck_payout(key="op1-payout-5", conv="AG_CONV_5")
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "mark_failed"}, format="json", **self._stepup())
        self.assertEqual(res.status_code, 409)

    def test_action_is_capability_and_stepup_gated(self):
        ft = self._stuck_payout(key="op1-payout-6", conv="AG_CONV_6")
        url = f"/api/ops/finops/transactions/{ft.pk}/action/"
        # Auditor lacks finops.retry.
        self.assertEqual(op_client(self.viewer).post(
            url, {"action": "requery"}, format="json").status_code, 403)
        # Finance has the capability but no step-up → refused.
        self.assertEqual(op_client(self.finance).post(
            url, {"action": "requery"}, format="json").status_code, 403)

    def test_queues_list_the_stuck_payout(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("pending"))
        self._stuck_payout(key="op1-payout-7", conv="AG_CONV_7")
        res = op_client(self.finance).get("/api/ops/finops/", {"minutes": 0})
        self.assertEqual(res.status_code, 200)
        self.assertGreaterEqual(res.data["counts"]["stuck_payouts"], 1)
        self.assertTrue(any(r["op_type"] == "DISBURSEMENT" for r in res.data["stuck_payouts"]))

    def _never_dispatched_payout(self, key="op1-retry-1"):
        """A payout stuck PENDING with no rail reference (never actually sent)."""
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        return FinancialTransaction.objects.create(
            op_type="DISBURSEMENT", amount=Decimal("500.00"), idempotency_key=key,
            initiated_by=self.member, recipient_phone="254700000201")

    def test_retry_payout_redispatches_never_sent_payout(self):
        from apps.payments.providers import registry
        from apps.payments.providers.fake import FakeProvider
        registry.use_provider(FakeProvider())   # implements initiate_payout
        ft = self._never_dispatched_payout()
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{ft.pk}/action/",
            {"action": "retry_payout"}, format="json", **self._stepup())
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["result"]["outcome"], "resent")
        ft.refresh_from_db()
        self.assertTrue(ft.mpesa_conversation_id)         # dispatched to the rail
        self.assertEqual(ft.state, "PROCESSING")

    def test_retry_payout_guards(self):
        from apps.payments.providers import registry
        registry.use_provider(_StubProvider("pending"))
        # Already dispatched (has a conversation id) → must Requery, not re-send.
        dispatched = self._stuck_payout(key="op1-retry-2", conv="AG_CONV_R2")
        res = op_client(self.finance).post(
            f"/api/ops/finops/transactions/{dispatched.pk}/action/",
            {"action": "retry_payout"}, format="json", **self._stepup())
        self.assertEqual(res.status_code, 409)
        dispatched.refresh_from_db()
        self.assertEqual(dispatched.state, "PROCESSING")


class MakerCheckerTests(TestCase):
    """OP-3 Part 2: reversals are two-person. A maker requests; a *different*
    operator approves, which executes the reversal attributed to both."""

    def setUp(self):
        self.maker = make_staff("maker@imbank.co.ke", "finance")    # finops.reverse + approvals.decide
        self.checker = make_staff("checker@imbank.co.ke", "finance")
        self.auditor = make_staff("appr-view@imbank.co.ke", "auditor")  # approvals.view only
        self.member = get_user_model().objects.create_user(
            phone_number="254700000301", name="Otieno P")

    def _settled_payout(self, key="mc-payout-1"):
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger.posting_map import disbursement_lines
        ft = FinancialTransaction.objects.create(
            op_type="DISBURSEMENT", amount=Decimal("3000.00"), idempotency_key=key,
            initiated_by=self.member, recipient_phone="254700000301",
            mpesa_conversation_id=f"{key}-conv", mpesa_receipt=f"{key}-rcpt",
        )
        ft.transition_to("PROCESSING")
        ft.transition_to("SUCCESS")
        post_journal(
            idempotency_key=f"{key}-journal", op_type="DISBURSEMENT",
            lines=disbursement_lines(member=self.member, fund_type="contribution",
                                     fund_id=777, amount=Money("3000.00")),
            narration="Settled disbursement", financial_transaction=ft,
        )
        return ft

    def test_full_maker_checker_reversal_flow(self):
        from apps.ledger.balances import trial_balance
        from apps.ledger.models import FinancialTransaction
        ft = self._settled_payout()

        # 1. Maker raises the reversal request (step-up gated). Nothing executes.
        req = op_client(self.maker).post(
            f"/api/ops/finops/transactions/{ft.pk}/reverse-request/",
            {"reason": "Duplicate payout — member already received funds."},
            format="json", **stepped_up(self.maker))
        self.assertEqual(req.status_code, 201)
        appr_id = req.data["approval_id"]
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")   # not touched yet

        # 2. Maker cannot approve their own request.
        deny = op_client(self.maker).post(
            f"/api/ops/approvals/{appr_id}/decide/",
            {"decision": "approve"}, format="json", **stepped_up(self.maker))
        self.assertEqual(deny.status_code, 409)
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")

        # 3. A second operator approves → the reversal executes, attributed to both.
        ok = op_client(self.checker).post(
            f"/api/ops/approvals/{appr_id}/decide/",
            {"decision": "approve", "note": "Confirmed with treasury."},
            format="json", **stepped_up(self.checker))
        self.assertEqual(ok.status_code, 200)
        self.assertEqual(ok.data["status"], "APPROVED")
        ft.refresh_from_db()
        self.assertEqual(ft.state, FinancialTransaction.State.REVERSED)
        self.assertTrue(trial_balance()["balanced"])   # reversal keeps books at zero
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.approval.approve").exists())

    def test_reject_leaves_movement_untouched(self):
        ft = self._settled_payout(key="mc-payout-2")
        req = op_client(self.maker).post(
            f"/api/ops/finops/transactions/{ft.pk}/reverse-request/",
            {"reason": "possibly wrong"}, format="json", **stepped_up(self.maker))
        appr_id = req.data["approval_id"]
        res = op_client(self.checker).post(
            f"/api/ops/approvals/{appr_id}/decide/",
            {"decision": "reject", "note": "Payout was correct."},
            format="json", **stepped_up(self.checker))
        self.assertEqual(res.data["status"], "REJECTED")
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")

    def test_expired_request_cannot_be_approved(self):
        from django.utils import timezone
        from datetime import timedelta
        from apps.backoffice import approvals
        from apps.backoffice.flagged_actions import ACTION_REVERSAL
        from apps.backoffice.models import OpsApprovalRequest
        ft = self._settled_payout(key="mc-payout-3")
        appr = approvals.require_approval(
            ACTION_REVERSAL, params={"ft_id": ft.pk, "reason": "x"},
            actor=self.maker, reason="x", target_id=str(ft.pk))
        OpsApprovalRequest.objects.filter(pk=appr.pk).update(
            expires_at=timezone.now() - timedelta(minutes=1))
        res = op_client(self.checker).post(
            f"/api/ops/approvals/{appr.pk}/decide/",
            {"decision": "approve"}, format="json", **stepped_up(self.checker))
        self.assertEqual(res.status_code, 409)
        ft.refresh_from_db()
        self.assertEqual(ft.state, "SUCCESS")

    def test_decide_is_capability_and_stepup_gated(self):
        from apps.backoffice import approvals
        from apps.backoffice.flagged_actions import ACTION_REVERSAL
        ft = self._settled_payout(key="mc-payout-4")
        appr = approvals.require_approval(
            ACTION_REVERSAL, params={"ft_id": ft.pk, "reason": "x"},
            actor=self.maker, reason="x", target_id=str(ft.pk))
        url = f"/api/ops/approvals/{appr.pk}/decide/"
        # Auditor lacks approvals.decide.
        self.assertEqual(op_client(self.auditor).post(
            url, {"decision": "approve"}, format="json").status_code, 403)
        # Checker holds it but without step-up → refused.
        self.assertEqual(op_client(self.checker).post(
            url, {"decision": "approve"}, format="json").status_code, 403)

    def test_reverse_request_rejects_unsettled_movement(self):
        # A PENDING movement is not reversible (only settled ones).
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        ft = FinancialTransaction.objects.create(
            op_type="DISBURSEMENT", amount=Decimal("10.00"), idempotency_key="mc-pending",
            initiated_by=self.member)
        res = op_client(self.maker).post(
            f"/api/ops/finops/transactions/{ft.pk}/reverse-request/",
            {"reason": "x"}, format="json", **stepped_up(self.maker))
        self.assertEqual(res.status_code, 409)


class IdentityAndReferenceTests(TestCase):
    """Member Number (searchable, stable) + unified transaction reference."""

    def setUp(self):
        self.member = get_user_model().objects.create_user(
            phone_number="254700000501", name="Amina H")
        self.viewer = make_staff("id-view@imbank.co.ke", "operations")   # users/tx view

    def test_member_number_is_generated_and_opaque(self):
        self.assertTrue(self.member.member_number)
        self.assertTrue(self.member.member_number.startswith("WM-"))
        # Unambiguous alphabet — no 0/1/I/L/O/U.
        body = self.member.member_number[3:]
        self.assertFalse(set(body) & set("01ILOU"))
        # Stable across a phone-number change.
        original = self.member.member_number
        self.member.phone_number = "254711111111"
        self.member.save()
        self.member.refresh_from_db()
        self.assertEqual(self.member.member_number, original)

    def test_member_is_searchable_by_member_number(self):
        mn = self.member.member_number
        res = op_client(self.viewer).get("/api/ops/users/", {"q": mn})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["results"][0]["id"], self.member.pk)
        self.assertEqual(res.data["results"][0]["member_number"], mn)
        # ⌘K federated search finds them too.
        gs = op_client(self.viewer).get("/api/ops/search/", {"q": mn})
        self.assertTrue(any(r["type"] == "user" and r["id"] == self.member.pk
                            for r in gs.data["results"]))

    def test_transaction_reference_unified_and_searchable(self):
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        ft = FinancialTransaction.objects.create(
            op_type="CONTRIBUTION", amount=Decimal("10.00"), idempotency_key="idref-1",
            initiated_by=self.member, mpesa_receipt="UG98TARRBR")
        expected = f"WEPL-TXN-{ft.pk:06d}"
        self.assertEqual(ft.reference, expected)

        # Registry search by the member-facing reference resolves to the FT.
        for term in (expected, str(ft.pk), f"wepl-txn-{ft.pk}"):
            res = op_client(self.viewer).get("/api/ops/transactions/", {"q": term})
            self.assertEqual(res.data["count"], 1, term)
            self.assertEqual(res.data["results"][0]["reference"], expected)

        # …and by the M-Pesa receipt (the other handle the member sees).
        res = op_client(self.viewer).get("/api/ops/transactions/", {"q": "UG98TARRBR"})
        self.assertEqual(res.data["count"], 1)

        # ⌘K global search now includes transactions.
        gs = op_client(self.viewer).get("/api/ops/search/", {"q": expected})
        self.assertTrue(any(r["type"] == "transaction" and r["id"] == ft.pk
                            for r in gs.data["results"]))

    def test_contribution_transaction_links_ft_and_mobile_ref_matches(self):
        # The mobile serializer's platform_ref must equal the FT reference (both
        # sides quote the same handle).
        from apps.contributions.serializers import ContributionTransactionSerializer
        from apps.contributions.services import ContributionService
        from apps.contributions.tests import approve_kyc
        approve_kyc(self.member)   # contribute() requires Tier-1
        contrib = ContributionService.create_contribution(self.member, {"title": "Ref Pool"})
        tx = ContributionService.contribute(
            self.member, contrib.id, 10, mpesa_receipt="RCPTUNIFY")
        tx.refresh_from_db()
        self.assertIsNotNone(tx.financial_transaction_id)
        ref = ContributionTransactionSerializer(tx).data["platform_ref"]
        self.assertEqual(ref, f"WEPL-TXN-{tx.financial_transaction_id:06d}")


class ExportsTests(TestCase):
    """OP-4: streamed-CSV exports — capability-gated, audited, correct content."""

    def setUp(self):
        self.member = get_user_model().objects.create_user(
            phone_number="254700000401", name="Njeri K")
        self.finance = make_staff("exp-fin@imbank.co.ke", "finance")     # reporting/ledger.export
        self.auditor = make_staff("exp-aud@imbank.co.ke", "auditor")     # audit/reporting/ledger.export
        self.support = make_staff("exp-sup@imbank.co.ke", "support")     # none of the export caps

    @staticmethod
    def _body(res):
        return b"".join(res.streaming_content).decode()

    def test_transactions_export_streams_csv_and_audits(self):
        from decimal import Decimal
        from apps.ledger.models import FinancialTransaction
        FinancialTransaction.objects.create(
            op_type="CONTRIBUTION", amount=Decimal("100.00"), idempotency_key="exp-tx-1",
            initiated_by=self.member, mpesa_receipt="RCPTEXP1")
        res = op_client(self.finance).get("/api/ops/exports/transactions/")
        self.assertEqual(res.status_code, 200)
        self.assertIn("text/csv", res["Content-Type"])
        body = self._body(res)
        self.assertIn("idempotency_key", body)          # header
        self.assertIn("exp-tx-1", body)                 # the row
        self.assertIn("RCPTEXP1", body)
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.export.transactions").exists())
        # Support lacks reporting.export.
        self.assertEqual(op_client(self.support).get(
            "/api/ops/exports/transactions/").status_code, 403)

    def test_audit_export_gated_and_filtered(self):
        from apps.audit.services import AuditService
        AuditService.log("ops.test.export", actor=None, target_type="thing", target_id="1")
        res = op_client(self.auditor).get("/api/ops/exports/audit/", {"action": "ops.test"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("ops.test.export", self._body(res))
        # Finance holds no audit.export.
        self.assertEqual(op_client(self.finance).get("/api/ops/exports/audit/").status_code, 403)

    def test_member_statement_export(self):
        from apps.ledger.money import Money
        from apps.ledger.posting import post_journal
        from apps.ledger.posting_map import contribution_lines
        post_journal(
            idempotency_key="exp-stmt-j1", op_type="CONTRIBUTION",
            lines=contribution_lines(member=self.member, fund_type="contribution",
                                     fund_id=111, gross=Money("100.00")),
            narration="Statement contribution")
        res = op_client(self.finance).get(f"/api/ops/users/{self.member.pk}/statement/")
        self.assertEqual(res.status_code, 200)
        body = self._body(res)
        self.assertIn("account_code", body)             # header
        self.assertIn("Statement contribution", body)   # the member's line narration
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.export.member_statement").exists())
        # Support lacks ledger.export.
        self.assertEqual(op_client(self.support).get(
            f"/api/ops/users/{self.member.pk}/statement/").status_code, 403)


class HealthAndAlertingTests(TestCase):
    """OP-2: outbox browser + requeue, worker heartbeats, ops_alerts → StaffNotice
    bell (raise / dedupe / auto-resolve / dismiss)."""

    def setUp(self):
        self.dev = make_staff("dev-health@imbank.co.ke", "developer")     # health.view + act
        self.auditor = make_staff("aud-health@imbank.co.ke", "auditor")   # health.view only
        self.support = make_staff("sup-health@imbank.co.ke", "support")   # no health.view

    def _dead_event(self, etype="advance_approved"):
        from apps.core.models import OutboxEvent
        return OutboxEvent.objects.create(
            event_type=etype, payload={"user_id": 1}, status=OutboxEvent.Status.DEAD,
            attempts=5, last_error="boom")

    def test_outbox_browser_and_requeue(self):
        ev = self._dead_event()
        res = op_client(self.dev).get("/api/ops/health/outbox/", {"status": "DEAD"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["results"][0]["last_error"], "boom")
        # Support lacks health.view.
        self.assertEqual(op_client(self.support).get("/api/ops/health/outbox/").status_code, 403)
        # Requeue (health.act) resets the event to PENDING with a fresh attempt count.
        res = op_client(self.dev).post(f"/api/ops/health/outbox/{ev.id}/requeue/")
        self.assertEqual(res.status_code, 200)
        ev.refresh_from_db()
        self.assertEqual(ev.status, "PENDING")
        self.assertEqual(ev.attempts, 0)
        from apps.audit.models import AuditEvent
        self.assertTrue(AuditEvent.objects.filter(action="ops.health.outbox_requeued").exists())

    def test_requeue_guards(self):
        from apps.core.models import OutboxEvent
        pending = OutboxEvent.objects.create(event_type="x", payload={}, status="PENDING")
        # Only DEAD events can be requeued.
        self.assertEqual(op_client(self.dev).post(
            f"/api/ops/health/outbox/{pending.id}/requeue/").status_code, 409)
        # Auditor has health.view but not health.act.
        dead = self._dead_event()
        self.assertEqual(op_client(self.auditor).post(
            f"/api/ops/health/outbox/{dead.id}/requeue/").status_code, 403)

    def test_heartbeat_staleness(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.core import health
        from apps.core.models import WorkerHeartbeat
        task = "apps.core.tasks.process_outbox"
        health.stamp(task)
        rows = {r["task"]: r for r in health.heartbeats()}
        self.assertFalse(rows[task]["stale"])
        self.assertFalse(rows[task]["never_seen"])
        # Age it past its window → stale.
        WorkerHeartbeat.objects.filter(task_name=task).update(
            last_seen=timezone.now() - timedelta(seconds=10_000))
        self.assertIn(task, health.stale_tasks())

    def test_ops_alerts_raises_dedupes_and_resolves(self):
        from apps.backoffice.models import StaffNotice
        from apps.backoffice.tasks import ops_alerts
        from apps.core.models import OutboxEvent
        self._dead_event()
        r1 = ops_alerts()
        self.assertIn("outbox_dead", r1["breaches"])
        self.assertEqual(StaffNotice.objects.filter(
            key="outbox_dead", resolved_at__isnull=True).count(), 1)
        # A second run does not duplicate the open notice.
        r2 = ops_alerts()
        self.assertEqual(r2["raised"], 0)
        # Clear the condition → the notice auto-resolves.
        OutboxEvent.objects.filter(status="DEAD").update(status="PROCESSED")
        r3 = ops_alerts()
        self.assertEqual(r3["resolved"], 1)
        self.assertEqual(StaffNotice.objects.filter(
            key="outbox_dead", resolved_at__isnull=True).count(), 0)

    def test_notice_bell_and_dismiss(self):
        from apps.backoffice.models import StaffNotice
        n = StaffNotice.objects.create(key="outbox_dead", level="CRITICAL",
                                       title="Dead letters", message="inspect")
        # Any operator sees the bell (no extra capability).
        res = op_client(self.support).get("/api/ops/notices/")
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.data["count"], 1)
        self.assertEqual(res.data["critical"], 1)
        d = op_client(self.support).post(f"/api/ops/notices/{n.id}/dismiss/")
        self.assertEqual(d.status_code, 200)
        n.refresh_from_db()
        self.assertIsNotNone(n.dismissed_at)
        self.assertEqual(op_client(self.support).get("/api/ops/notices/").data["count"], 0)
