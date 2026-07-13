"""Organization spine tests (ADR-0026 Phase 0).

The spine is thin and additive: every community is born as (or backfilled with)
an Organization of archetype 'community', carrying the same tenant and a UUIDv7
external handle. Nothing user-facing changes."""
from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.organizations.models import (
    Organization, Program, ensure_organization_for_community, ensure_program,
)

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


class ProgramSpineTests(TestCase):
    """Program spine (ADR-0026): every fund is born as a Program of its
    operating Organization; the ledger's (fund_type, fund_id) anchoring is
    untouched."""

    def _user(self, phone):
        return _make_user(phone)

    def test_community_funds_are_born_as_programs(self):
        from apps.communities.services import CommunityService
        user = self._user("254700000811")
        community = CommunityService.create_community(
            user, {"name": "Program Chama", "has_welfare_fund": True,
                   "has_shares_fund": True})
        org = community.organization

        welfare = community.welfare_funds.first()
        shares = community.shares_fund
        self.assertEqual(welfare.program.program_type, Program.ProgramType.WELFARE)
        self.assertEqual(shares.program.program_type, Program.ProgramType.SHARES)
        # Programs belong to the community's Organization and share its tenant.
        for program in (welfare.program, shares.program):
            self.assertEqual(program.organization_id, org.id)
            self.assertEqual(program.tenant_id, community.tenant_id)
            self.assertEqual(program.uid.version, 7)

    def test_contribution_is_born_as_a_program(self):
        from apps.contributions.services import ContributionService
        user = self._user("254700000812")
        contribution = ContributionService.create_contribution(
            user, {"title": "Open Pool"})   # standalone: no community
        program = contribution.program
        self.assertEqual(program.program_type, Program.ProgramType.CONTRIBUTION)
        self.assertEqual(program.name, "Open Pool")
        self.assertIsNone(program.organization_id)   # personal/open pool
        # Reverse accessor: profile hangs off the spine.
        self.assertEqual(program.contribution_profile, contribution)

    def test_community_contribution_links_to_its_organization(self):
        from apps.communities.services import CommunityService
        from apps.contributions.services import ContributionService
        user = self._user("254700000813")
        community = CommunityService.create_community(user, {"name": "Org Chama"})
        contribution = ContributionService.create_contribution(
            user, {"title": "Org Pool", "community": community, "visibility": "closed"})
        self.assertEqual(contribution.program.organization_id,
                         community.organization_id)

    def test_ensure_program_is_idempotent_and_backfills(self):
        from apps.contributions.models import Contribution
        from apps.contributions.services import ContributionService
        user = self._user("254700000814")
        contribution = ContributionService.create_contribution(
            user, {"title": "Idem Pool"})
        first = contribution.program
        self.assertEqual(ensure_program(fund=contribution,
                                        program_type='contribution').id, first.id)
        # Pre-spine row (link cleared) — the same path the data migration walks.
        Contribution.objects.filter(pk=contribution.pk).update(program=None)
        contribution.refresh_from_db()
        again = ensure_program(fund=contribution, program_type='contribution')
        self.assertNotEqual(again.id, first.id)
        self.assertEqual(again.name, "Idem Pool")
