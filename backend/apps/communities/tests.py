"""Community test suite (ADR-0009 reference + platform-hardening P0).

Covers what the platform-hardening review flagged as missing for this app:
  * the centralized authorization policy (unit + over-the-wire),
  * membership lifecycle and the last-admin invariant,
  * cross-tenant isolation of community resources.
"""
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
from apps.core.policy import can, require
from apps.communities.models import Community, CommunityMembership
from apps.communities.services import CommunityService

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone: str, **kwargs):
    return User.objects.create(phone_number=phone, **kwargs)


def active_client(user) -> APIClient:
    """APIClient carrying an active-stage token so IsActiveSession is satisfied."""
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class CommunityPolicyTests(TestCase):
    """The capability matrix decides authorization purely from role/rank."""

    def setUp(self):
        self.creator   = make_user("254700000001")
        self.admin     = make_user("254700000002")
        self.treasurer = make_user("254700000003")
        self.member    = make_user("254700000004")
        self.outsider  = make_user("254700000005")
        self.c = CommunityService.create_community(self.creator, {"name": "Test Chama"})
        CommunityMembership.objects.create(user=self.admin,     community=self.c, role=Role.ADMIN)
        CommunityMembership.objects.create(user=self.treasurer, community=self.c, role=Role.TREASURER)
        CommunityMembership.objects.create(user=self.member,    community=self.c, role=Role.MEMBER)

    def test_view_requires_active_membership(self):
        for u in (self.creator, self.admin, self.treasurer, self.member):
            self.assertTrue(can(u, "community.view", self.c))
        self.assertFalse(can(self.outsider, "community.view", self.c))

    def test_update_is_admin_or_creator_only(self):
        self.assertTrue(can(self.creator, "community.update", self.c))
        self.assertTrue(can(self.admin,   "community.update", self.c))
        self.assertFalse(can(self.treasurer, "community.update", self.c))
        self.assertFalse(can(self.member,    "community.update", self.c))

    def test_delete_is_creator_only(self):
        self.assertTrue(can(self.creator, "community.delete", self.c))
        self.assertFalse(can(self.admin,  "community.delete", self.c))

    def test_member_management_is_creator_only(self):
        for action in ("community.member.assign_role", "community.member.remove"):
            self.assertTrue(can(self.creator, action, self.c), action)
            self.assertFalse(can(self.admin,  action, self.c), action)
            self.assertFalse(can(self.member, action, self.c), action)

    def test_join_request_review_is_admin(self):
        self.assertTrue(can(self.admin,   "community.join_request.review", self.c))
        self.assertTrue(can(self.creator, "community.join_request.review", self.c))
        self.assertFalse(can(self.member, "community.join_request.review", self.c))

    def test_require_raises_permission_denied(self):
        with self.assertRaises(PermissionDenied):
            require(self.member, "community.update", self.c)
        require(self.creator, "community.update", self.c)  # allowed → no raise

    def test_anonymous_is_always_denied(self):
        self.assertFalse(can(AnonymousUser(), "community.view", self.c))

    def test_superuser_bypasses_policy(self):
        su = make_user("254700009999", is_superuser=True, is_staff=True)
        self.assertTrue(can(su, "community.delete", self.c))

    def test_unknown_action_is_a_config_error_not_an_allow(self):
        # Fail-closed: an unregistered action must never silently authorize.
        with self.assertRaises(KeyError):
            can(self.creator, "community.nonexistent", self.c)


class MembershipLifecycleTests(TestCase):

    def setUp(self):
        self.creator = make_user("254700000001")
        self.joiner  = make_user("254700000002")
        self.open_c = CommunityService.create_community(
            self.creator, {"name": "Open Chama", "is_private": False,
                           "join_policy": Community.JoinPolicy.OPEN},
        )

    def test_join_open_community(self):
        m = CommunityService.join_community(self.joiner, self.open_c)
        self.assertTrue(m.is_active)
        self.assertEqual(m.role, Role.MEMBER)

    def test_join_is_idempotent(self):
        CommunityService.join_community(self.joiner, self.open_c)
        CommunityService.join_community(self.joiner, self.open_c)  # no duplicate / no raise
        self.assertEqual(
            self.open_c.memberships.filter(user=self.joiner, is_active=True).count(), 1,
        )

    def test_private_community_cannot_be_joined_directly(self):
        private = CommunityService.create_community(
            make_user("254700000010"), {"name": "Private", "is_private": True},
        )
        with self.assertRaises(PermissionDenied):
            CommunityService.join_community(self.joiner, private)

    def test_member_cap_enforced(self):
        capped = CommunityService.create_community(
            make_user("254700000011"),
            {"name": "Capped", "is_private": False,
             "join_policy": Community.JoinPolicy.OPEN, "max_members": 1},
        )  # creator already fills the single slot
        with self.assertRaises(ValidationError):
            CommunityService.join_community(self.joiner, capped)

    def test_last_admin_cannot_leave(self):
        # Creator is the only admin — leaving would orphan the community.
        with self.assertRaises(ValidationError):
            CommunityService.leave_community(self.creator, self.open_c)

    def test_demoting_non_last_admin_is_allowed(self):
        other = make_user("254700000020")
        m = CommunityMembership.objects.create(user=other, community=self.open_c, role=Role.ADMIN)
        # Two admins now (creator + other) — demoting one is fine.
        CommunityService.assign_role(self.creator, self.open_c, m.id, Role.MEMBER)
        m.refresh_from_db()
        self.assertEqual(m.role, Role.MEMBER)
        self.assertEqual(self.open_c.active_admin_count(), 1)


class CommunityAuthzApiTests(TestCase):
    """Authorization enforced over the wire through the policy layer."""

    def setUp(self):
        self.creator = make_user("254700000001")
        self.member  = make_user("254700000002")
        self.c = CommunityService.create_community(self.creator, {"name": "Chama"})
        CommunityMembership.objects.create(user=self.member, community=self.c, role=Role.MEMBER)

    def test_member_cannot_update(self):
        r = active_client(self.member).patch(
            f"/api/communities/{self.c.id}/update/", {"name": "Hacked"}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_creator_can_update(self):
        r = active_client(self.creator).patch(
            f"/api/communities/{self.c.id}/update/", {"name": "New Name"}, format="json")
        self.assertEqual(r.status_code, 200)
        self.c.refresh_from_db()
        self.assertEqual(self.c.name, "New Name")

    def test_member_cannot_delete(self):
        r = active_client(self.member).delete(f"/api/communities/{self.c.id}/delete/")
        self.assertEqual(r.status_code, 403)

    def test_member_cannot_remove_another_member(self):
        victim = make_user("254700000003")
        vm = CommunityMembership.objects.create(user=victim, community=self.c, role=Role.MEMBER)
        r = active_client(self.member).delete(
            f"/api/communities/{self.c.id}/members/{vm.id}/")
        self.assertEqual(r.status_code, 403)
        vm.refresh_from_db()
        self.assertTrue(vm.is_active)  # untouched

    def test_unauthenticated_is_rejected(self):
        r = APIClient().patch(
            f"/api/communities/{self.c.id}/update/", {"name": "x"}, format="json")
        self.assertIn(r.status_code, (401, 403))


class CommunityTenantIsolationTests(TestCase):
    """A request pinned to one tenant must not reach another tenant's community."""

    def test_guard_blocks_cross_tenant_access(self):
        from apps.tenants.models import Tenant
        from apps.tenants.rls import set_current_tenant, clear_current_tenant
        from apps.tenants.guards import guard_tenant

        tenant_a = Tenant.objects.create(slug="org-a", name="Org A")
        tenant_b = Tenant.objects.create(slug="org-b", name="Org B")
        community_b = Community.objects.create(
            name="B's Chama", created_by=make_user("254700000030"), tenant=tenant_b,
        )

        set_current_tenant(tenant_a.id)
        try:
            with self.assertRaises(PermissionDenied):
                guard_tenant(community_b.tenant_id,
                             resource_type="community", resource_id=community_b.id)
            guard_tenant(tenant_a.id, resource_type="community", resource_id=1)  # same tenant → ok
        finally:
            clear_current_tenant()


class OwnershipTransferTests(TestCase):
    """ADR-0011 — ownership transfer + the last-admin/ownership invariants."""

    def setUp(self):
        self.owner   = make_user("254700000001")
        self.admin   = make_user("254700000002")
        self.member  = make_user("254700000003")
        self.c = CommunityService.create_community(self.owner, {"name": "Chama"})
        self.m_admin  = CommunityMembership.objects.create(
            user=self.admin, community=self.c, role=Role.ADMIN)
        self.m_member = CommunityMembership.objects.create(
            user=self.member, community=self.c, role=Role.MEMBER)

    def test_only_owner_may_transfer(self):
        with self.assertRaises(PermissionDenied):
            CommunityService.transfer_ownership(self.admin, self.c, self.m_member.id)

    def test_cannot_transfer_to_non_member(self):
        outsider = make_user("254700000004")
        m = CommunityMembership.objects.create(
            user=outsider, community=self.c, role=Role.MEMBER, is_active=False)
        with self.assertRaises(ValidationError):
            CommunityService.transfer_ownership(self.owner, self.c, m.id)

    def test_cannot_transfer_to_self(self):
        own = self.c.memberships.get(user=self.owner)
        with self.assertRaises(ValidationError):
            CommunityService.transfer_ownership(self.owner, self.c, own.id)

    def test_successful_transfer_promotes_and_keeps_former_owner_admin(self):
        CommunityService.transfer_ownership(self.owner, self.c, self.m_member.id)
        self.c.refresh_from_db()
        # ownership moved
        self.assertEqual(self.c.created_by_id, self.member.id)
        # new owner is an admin
        self.m_member.refresh_from_db()
        self.assertEqual(self.m_member.role, Role.ADMIN)
        # former owner stays an admin → never below one admin
        former = self.c.memberships.get(user=self.owner)
        self.assertEqual(former.role, Role.ADMIN)
        self.assertGreaterEqual(self.c.active_admin_count(), 1)

    def test_capabilities_follow_ownership(self):
        # before: only the owner can delete
        self.assertTrue(can(self.owner, "community.delete", self.c))
        self.assertFalse(can(self.member, "community.delete", self.c))
        CommunityService.transfer_ownership(self.owner, self.c, self.m_member.id)
        self.c.refresh_from_db()
        # after: the new owner holds creator-only capabilities, the old owner does not
        self.assertTrue(can(self.member, "community.delete", self.c))
        self.assertFalse(can(self.owner, "community.delete", self.c))

    def test_transfer_via_api(self):
        r = active_client(self.owner).post(
            f"/api/communities/{self.c.id}/transfer-ownership/",
            {"membership_id": self.m_admin.id}, format="json")
        self.assertEqual(r.status_code, 200)
        self.c.refresh_from_db()
        self.assertEqual(self.c.created_by_id, self.admin.id)

    def test_non_owner_transfer_via_api_is_forbidden(self):
        r = active_client(self.admin).post(
            f"/api/communities/{self.c.id}/transfer-ownership/",
            {"membership_id": self.m_member.id}, format="json")
        self.assertEqual(r.status_code, 403)

    def test_superuser_can_transfer_to_recover_orphan(self):
        operator = make_user("254700009999")
        operator.is_superuser = True
        operator.is_staff = True
        operator.save(update_fields=["is_superuser", "is_staff"])
        # operator is not a member, but may reassign ownership (orphan recovery)
        CommunityService.transfer_ownership(operator, self.c, self.m_admin.id)
        self.c.refresh_from_db()
        self.assertEqual(self.c.created_by_id, self.admin.id)

    def test_no_pinned_tenant_is_unrestricted(self):
        # Staff/system contexts (no tenant pinned) operate across tenants.
        from apps.tenants.models import Tenant
        from apps.tenants.rls import clear_current_tenant
        from apps.tenants.guards import guard_tenant

        other = Tenant.objects.create(slug="org-c", name="Org C")
        clear_current_tenant()
        guard_tenant(other.id, resource_type="community", resource_id=1)  # must not raise


class CommunityEnrichmentTests(TestCase):
    """The my-communities list carries real per-community highlights:
    total_managed (ledger), pending_count, last_activity."""

    def setUp(self):
        from datetime import date
        from apps.users.models import KYCProfile
        self.creator = make_user("254700020001", is_phone_verified=True)
        KYCProfile.objects.create(  # → Tier 1 so contribute() (money path) is allowed
            user=self.creator, status="approved", given_names="T", surname="U",
            id_number="IDENR1", date_of_birth=date(1990, 1, 1),
        )
        self.community = CommunityService.create_community(self.creator, {"name": "Chama"})

    def _mine(self):
        r = active_client(self.creator).get("/api/communities/")
        self.assertEqual(r.status_code, 200)
        return next(c for c in r.json() if c["id"] == self.community.id)

    def test_fields_present_and_default(self):
        row = self._mine()
        # A brand-new community with no funds/requests: zeroed but present.
        self.assertEqual(Decimal(row["total_managed"]), Decimal("0"))
        self.assertEqual(row["pending_count"], 0)
        self.assertIsNotNone(row["last_activity"])

    def test_total_managed_reflects_ledger(self):
        from apps.contributions.services.contribution import ContributionService
        contribution = ContributionService.create_contribution(
            self.creator, {"title": "Pool", "contribution_type": "POOL",
                           "visibility": "open", "community": self.community})
        ContributionService.contribute(self.creator, contribution.id, 500)
        self.assertEqual(Decimal(self._mine()["total_managed"]), Decimal("500"))

    def test_pending_count_counts_join_requests(self):
        joiner = make_user("254700020002")
        CommunityService.request_to_join(joiner, self.community)
        self.assertEqual(self._mine()["pending_count"], 1)


class CommunityMuteTests(TestCase):
    """Per-community notification mute: endpoint sets the flag and the serializer
    reflects it for the requesting member."""

    def setUp(self):
        self.creator = make_user("254700000601")
        self.c = CommunityService.create_community(self.creator, {"name": "Chama"})

    def test_mute_toggles_flag_and_serializer(self):
        r = active_client(self.creator).post(
            f"/api/communities/{self.c.id}/mute/", {"muted": True}, format="json")
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["muted"])
        self.assertTrue(CommunityMembership.objects.get(
            user=self.creator, community=self.c).notifications_muted)
        # Serializer reflects it
        detail = active_client(self.creator).get(f"/api/communities/{self.c.id}/")
        self.assertTrue(detail.json()["is_muted"])
        # Unmute
        r2 = active_client(self.creator).post(
            f"/api/communities/{self.c.id}/mute/", {"muted": False}, format="json")
        self.assertFalse(r2.json()["muted"])

    def test_non_member_cannot_mute(self):
        outsider = make_user("254700000602")
        r = active_client(outsider).post(
            f"/api/communities/{self.c.id}/mute/", {"muted": True}, format="json")
        self.assertEqual(r.status_code, 404)


class Sprint1SafetyTests(TestCase):
    """Communities audit Sprint 1: safe delete (CR-1), lifecycle (CR-2),
    rejoin cooling-off clock (H-1), owner-departure rule (H-2)."""

    def setUp(self):
        self.owner  = make_user("254700000061")
        self.other  = make_user("254700000062")
        self.c = CommunityService.create_community(
            self.owner, {"name": "Chama", "is_private": False,
                         "join_policy": Community.JoinPolicy.OPEN,
                         "has_welfare_fund": True, "cooling_off_days": 30})

    # ── CR-1: safe delete ──────────────────────────────────────────────────

    def test_shell_delete_still_works_and_cleans_empty_funds(self):
        CommunityService.delete_community(self.owner, self.c)
        self.assertFalse(Community.objects.filter(pk=self.c.pk).exists())

    def test_delete_refused_once_money_moved(self):
        from decimal import Decimal
        from apps.contributions.models import WelfareContribution
        fund = self.c.welfare_funds.first()
        WelfareContribution.objects.create(
            fund=fund, user=self.owner, amount=Decimal("100.00"))
        with self.assertRaisesMessage(ValidationError, "financial history"):
            CommunityService.delete_community(self.owner, self.c)
        self.assertTrue(Community.objects.filter(pk=self.c.pk).exists())

    # ── CR-2: lifecycle ────────────────────────────────────────────────────

    def test_archived_community_freezes_creation_paths(self):
        CommunityService.archive_community(self.owner, self.c)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, Community.Status.ARCHIVED)
        with self.assertRaises(ValidationError):
            CommunityService.join_community(self.other, self.c)
        with self.assertRaises(ValidationError):
            CommunityService.request_to_join(self.other, self.c)
        # Owner can restore.
        CommunityService.unarchive_community(self.owner, self.c)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, Community.Status.ACTIVE)
        CommunityService.join_community(self.other, self.c)

    def test_archive_is_owner_only(self):
        CommunityService.join_community(self.other, self.c)
        m = self.c.memberships.get(user=self.other)
        m.role = Role.ADMIN
        m.save(update_fields=["role"])
        with self.assertRaises(PermissionDenied):
            CommunityService.archive_community(self.other, self.c)

    def test_suspension_blocks_contribution_creation_and_is_ops_only(self):
        CommunityService.suspend_community(self.c, reason="test freeze")
        self.c.refresh_from_db()
        from apps.contributions.services import ContributionService
        with self.assertRaises(ValidationError):
            ContributionService.create_contribution(
                self.owner, {"name": "Pool", "community": self.c})
        # Suspended cannot be archived by the owner.
        with self.assertRaises(ValidationError):
            CommunityService.archive_community(self.owner, self.c)
        CommunityService.unsuspend_community(self.c)
        self.c.refresh_from_db()
        self.assertEqual(self.c.status, Community.Status.ACTIVE)

    def test_discover_hides_non_active(self):
        CommunityService.archive_community(self.owner, self.c)
        res = active_client(self.other).get("/api/communities/discover/")
        ids = [r["id"] for r in res.json()["results"]]
        self.assertNotIn(self.c.id, ids)

    # ── H-1: rejoin restarts the cooling-off clock ─────────────────────────

    def test_rejoin_resets_cooling_off_clock(self):
        from datetime import timedelta
        from django.utils import timezone
        from apps.communities.services import check_cooling_off

        CommunityService.join_community(self.other, self.c)
        m = self.c.memberships.get(user=self.other)
        # Age the original join beyond the cooling-off window.
        CommunityMembership.objects.filter(pk=m.pk).update(
            joined_at=timezone.now() - timedelta(days=90))
        check_cooling_off(self.other, self.c, "welfare_claim")  # eligible

        CommunityService.leave_community(self.other, self.c)
        CommunityService.join_community(self.other, self.c)     # rejoin today
        with self.assertRaisesMessage(ValidationError, "must wait"):
            check_cooling_off(self.other, self.c, "welfare_claim")

    # ── H-2: the owner cannot leave without transferring ───────────────────

    def test_owner_cannot_leave_without_transfer(self):
        CommunityService.join_community(self.other, self.c)
        m = self.c.memberships.get(user=self.other)
        m.role = Role.ADMIN
        m.save(update_fields=["role"])
        with self.assertRaisesMessage(ValidationError, "Transfer ownership"):
            CommunityService.leave_community(self.owner, self.c)
        # After transfer, the former owner may leave.
        CommunityService.transfer_ownership(self.owner, self.c, m.id)
        self.c.refresh_from_db()
        CommunityService.leave_community(self.owner, self.c)
        self.assertFalse(self.c.memberships.filter(
            user=self.owner, is_active=True).exists())


class Sprint2GovernanceTests(TestCase):
    """Communities audit Sprint 2: invite_permission enforcement + rotation
    (H-3), ban semantics (H-4), settings audit diff (M-1), deactivated-user
    authority (M-4)."""

    def setUp(self):
        self.owner  = make_user("254700000071")
        self.admin  = make_user("254700000072")
        self.member = make_user("254700000073")
        self.c = CommunityService.create_community(
            self.owner, {"name": "Chama", "is_private": False,
                         "join_policy": Community.JoinPolicy.OPEN})
        CommunityMembership.objects.create(user=self.admin,  community=self.c, role=Role.ADMIN)
        CommunityMembership.objects.create(user=self.member, community=self.c, role=Role.MEMBER)

    def _code_visible_to(self, user):
        res = active_client(user).get(f"/api/communities/{self.c.id}/")
        return res.json().get("invite_code")

    # ── H-3: invite_permission enforced + rotation ─────────────────────────

    def test_invite_code_visibility_honours_setting(self):
        # members: everyone active sees it
        Community.objects.filter(pk=self.c.pk).update(invite_permission="members")
        self.assertIsNotNone(self._code_visible_to(self.member))
        # admins: plain member no longer sees it
        Community.objects.filter(pk=self.c.pk).update(invite_permission="admins")
        self.assertIsNone(self._code_visible_to(self.member))
        self.assertIsNotNone(self._code_visible_to(self.admin))
        # creator: even admins are blind
        Community.objects.filter(pk=self.c.pk).update(invite_permission="creator")
        self.assertIsNone(self._code_visible_to(self.admin))
        self.assertIsNotNone(self._code_visible_to(self.owner))

    def test_rotation_regenerates_and_respects_setting(self):
        old_code = self.c.invite_code
        res = active_client(self.admin).post(f"/api/communities/{self.c.id}/invite/rotate/")
        self.assertEqual(res.status_code, 200)
        new_code = res.json()["invite_code"]
        self.assertNotEqual(new_code, old_code)
        # Old code is dead.
        self.assertEqual(
            active_client(self.member).get(f"/api/communities/invite/{old_code}/").status_code, 404)
        # Creator-only sharing → admin may not rotate either.
        Community.objects.filter(pk=self.c.pk).update(invite_permission="creator")
        res = active_client(self.admin).post(f"/api/communities/{self.c.id}/invite/rotate/")
        self.assertEqual(res.status_code, 403)
        # Plain member never rotates.
        res = active_client(self.member).post(f"/api/communities/{self.c.id}/invite/rotate/")
        self.assertEqual(res.status_code, 403)

    # ── H-4: ban semantics ─────────────────────────────────────────────────

    def test_removed_member_can_rejoin_but_banned_cannot(self):
        m = self.c.memberships.get(user=self.member)
        CommunityService.remove_member(self.owner, self.c, m.id)          # plain removal
        m.refresh_from_db()
        self.assertEqual(m.member_status, "removed")
        CommunityService.join_community(self.member, self.c)              # revolving door OK
        self.assertTrue(self.c.memberships.get(user=self.member).is_active)

        m = self.c.memberships.get(user=self.member)
        CommunityService.remove_member(self.owner, self.c, m.id, ban=True)
        m.refresh_from_db()
        self.assertEqual(m.member_status, "banned")
        with self.assertRaises(PermissionDenied):
            CommunityService.join_community(self.member, self.c)
        with self.assertRaises(PermissionDenied):
            CommunityService.request_to_join(self.member, self.c)

    def test_ban_via_endpoint_and_leave_marks_left(self):
        m = self.c.memberships.get(user=self.member)
        res = active_client(self.owner).delete(
            f"/api/communities/{self.c.id}/members/{m.id}/?ban=true")
        self.assertEqual(res.status_code, 204)
        m.refresh_from_db()
        self.assertEqual(m.member_status, "banned")

        m2 = self.c.memberships.get(user=self.admin)
        CommunityService.leave_community(self.admin, self.c)
        m2.refresh_from_db()
        self.assertEqual(m2.member_status, "left")

    # ── M-1: settings changes audited with old→new diff ───────────────────

    def test_settings_update_audits_diff(self):
        from apps.audit.models import AuditEvent
        CommunityService.update_settings(self.owner, self.c,
                                         {"join_policy": "request", "ignored_field": "x"})
        ev = AuditEvent.objects.filter(action="community.settings_updated").latest("created_at")
        self.assertEqual(ev.metadata["changes"]["join_policy"]["old"], "open")
        self.assertEqual(ev.metadata["changes"]["join_policy"]["new"], "request")
        self.assertNotIn("ignored_field", ev.metadata["changes"])

    # ── M-4: deactivated users hold no authority weight ───────────────────

    def test_deactivated_admin_does_not_satisfy_last_admin_guard(self):
        # Two admins; deactivate one at the platform level.
        self.admin.is_active = False
        self.admin.save(update_fields=["is_active"])
        self.assertEqual(self.c.active_admin_count(), 1)  # only the owner counts
        # Owner is now effectively the last admin — and (Sprint 1) owners must
        # transfer before leaving anyway; the guard math no longer counts ghosts.
