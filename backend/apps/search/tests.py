"""Search tests (ADR-0017): ranking basics + permission filtering (never leak)."""
from django.contrib.auth import get_user_model
from django.test import TestCase
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import Community, CommunityMembership
from apps.communities.services import CommunityService
from apps.contributions.services import ContributionService
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM
from apps.users.models import PrivacyPreferences

from .services import SearchService

User = get_user_model()
Role = CommunityMembership.Role


def make_user(phone, name=""):
    u = User.objects.create(phone_number=phone, name=name)
    u.set_pin("123456")
    return u


def active_client(user):
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    c = APIClient()
    c.force_authenticate(user=user, token=token)
    return c


class CommunitySearchPermissionTests(TestCase):
    def setUp(self):
        self.owner = make_user("254700000001")
        self.outsider = make_user("254700000002")
        self.public = CommunityService.create_community(
            self.owner, {"name": "Nairobi Savers", "is_private": False})
        self.private = CommunityService.create_community(
            self.owner, {"name": "Nairobi Secret Club", "is_private": True})

    def test_public_community_found_by_anyone(self):
        res = SearchService.search(self.outsider, "Nairobi")["communities"]
        names = {c["name"] for c in res}
        self.assertIn("Nairobi Savers", names)

    def test_private_community_hidden_from_non_member(self):
        res = SearchService.search(self.outsider, "Nairobi")["communities"]
        names = {c["name"] for c in res}
        self.assertNotIn("Nairobi Secret Club", names)

    def test_private_community_visible_to_member(self):
        res = SearchService.search(self.owner, "Nairobi")["communities"]
        names = {c["name"] for c in res}
        self.assertIn("Nairobi Secret Club", names)


class ContributionSearchPermissionTests(TestCase):
    def setUp(self):
        self.owner = make_user("254700000001")
        self.outsider = make_user("254700000002")
        self.community = CommunityService.create_community(self.owner, {"name": "Chama"})
        self.open_c = ContributionService.create_contribution(
            self.owner, {"title": "Harambee Fund", "contribution_type": "POOL",
                         "visibility": "open"})
        self.closed_c = ContributionService.create_contribution(
            self.owner, {"title": "Harambee Private", "contribution_type": "POOL",
                         "visibility": "closed", "community": self.community})

    def test_open_contribution_found(self):
        res = SearchService.search(self.outsider, "Harambee")["contributions"]
        self.assertIn("Harambee Fund", {c["title"] for c in res})

    def test_closed_contribution_hidden_from_outsider(self):
        res = SearchService.search(self.outsider, "Harambee")["contributions"]
        self.assertNotIn("Harambee Private", {c["title"] for c in res})

    def test_closed_contribution_visible_to_creator(self):
        res = SearchService.search(self.owner, "Harambee")["contributions"]
        self.assertIn("Harambee Private", {c["title"] for c in res})


class UserSearchPrivacyTests(TestCase):
    def setUp(self):
        self.searcher = make_user("254700000001", name="Searcher")
        self.alice = make_user("254700000010", name="Alice Wanjiru")
        self.bob = make_user("254700000011", name="Bob Hidden")
        PrivacyPreferences.objects.create(user=self.bob, discoverable=False)

    def test_discoverable_user_found_by_name(self):
        res = SearchService.search(self.searcher, "Alice")["users"]
        self.assertIn(self.alice.id, {u["id"] for u in res})

    def test_non_discoverable_user_excluded(self):
        res = SearchService.search(self.searcher, "Bob")["users"]
        self.assertNotIn(self.bob.id, {u["id"] for u in res})

    def test_found_by_exact_phone(self):
        res = SearchService.search(self.searcher, "254700000010")["users"]
        self.assertIn(self.alice.id, {u["id"] for u in res})


class SearchApiTests(TestCase):
    def setUp(self):
        self.user = make_user("254700000001")
        CommunityService.create_community(self.user, {"name": "Kilimani Group", "is_private": False})

    def test_empty_query_returns_empty_groups(self):
        r = active_client(self.user).get("/api/search/?q=")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.json()["results"]["communities"], [])

    def test_type_filter(self):
        r = active_client(self.user).get("/api/search/?q=Kilimani&type=communities")
        body = r.json()["results"]
        self.assertIn("communities", body)
        self.assertNotIn("users", body)

    def test_search_requires_auth(self):
        self.assertIn(APIClient().get("/api/search/?q=x").status_code, (401, 403))
