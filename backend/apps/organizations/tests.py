"""Organization spine tests (ADR-0026 Phase 0).

The spine is thin and additive: every community is born as (or backfilled with)
an Organization of archetype 'community', carrying the same tenant and a UUIDv7
external handle. Nothing user-facing changes."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import Organization, ensure_organization_for_community

User = get_user_model()


def _make_user(phone="254700000801"):
    u = User.objects.create(phone_number=phone)
    u.set_pin("123456")
    return u


class OrganizationSpineTests(TestCase):

    def _community(self, user, name="Spine Chama"):
        from apps.communities.services import CommunityService
        return CommunityService.create_community(user, {"name": name})

    def test_created_community_is_born_as_an_organization(self):
        community = self._community(_make_user())
        self.assertIsNotNone(community.organization_id)
        org = community.organization
        self.assertEqual(org.archetype, Organization.Archetype.COMMUNITY)
        self.assertEqual(org.name, community.name)
        self.assertEqual(org.tenant_id, community.tenant_id)  # hosting boundary inherited
        # Reverse: the archetype profile hangs off the spine.
        self.assertEqual(org.community_profile, community)

    def test_organization_uid_is_uuidv7(self):
        community = self._community(_make_user("254700000802"), name="UID Chama")
        uid = community.organization.uid
        self.assertEqual(uid.version, 7)
        self.assertIn(uid.variant, ("specified in RFC 4122",))

    def test_ensure_is_idempotent(self):
        community = self._community(_make_user("254700000803"), name="Idem Chama")
        first = community.organization
        again = ensure_organization_for_community(community)
        self.assertEqual(first.id, again.id)
        self.assertEqual(Organization.objects.filter(community_profile=community).count(), 1)

    def test_ensure_backfills_a_pre_spine_community(self):
        # Simulate a pre-ADR-0026 row (organization link cleared) — the same
        # path the data migration walks.
        from apps.communities.models import Community
        community = self._community(_make_user("254700000804"), name="Legacy Chama")
        org_count = Organization.objects.count()
        Community.objects.filter(pk=community.pk).update(organization=None)
        community.refresh_from_db()

        org = ensure_organization_for_community(community)
        self.assertEqual(org.archetype, Organization.Archetype.COMMUNITY)
        self.assertEqual(org.tenant_id, community.tenant_id)
        self.assertEqual(Organization.objects.count(), org_count + 1)
