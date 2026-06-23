"""Community test suite (ADR-0009 reference + platform-hardening P0).

Covers what the platform-hardening review flagged as missing for this app:
  * the centralized authorization policy (unit + over-the-wire),
  * membership lifecycle and the last-admin invariant,
  * cross-tenant isolation of community resources.
"""
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
