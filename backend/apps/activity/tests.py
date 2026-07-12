"""
Activity feed tests (ADR-0016): typed-event rendering, visibility rule, the
back-compat shim, and cursor-paginated feed endpoints.
"""
from rest_framework.test import APIClient, APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from apps.communities.models import Community, CommunityMembership
from apps.tenants.models import Tenant
from apps.users.models import User
from apps.users.auth import STAGE_ACTIVE, STAGE_CLAIM

from .models import Activity
from .render import render_activity
from .services import ActivityService


def make_user(phone, **kwargs):
    return User.objects.create(phone_number=phone, **kwargs)


def active_client(user) -> APIClient:
    token = AccessToken.for_user(user)
    token[STAGE_CLAIM] = STAGE_ACTIVE
    client = APIClient()
    client.force_authenticate(user=user, token=token)
    return client


class ActivityRenderTests(APITestCase):
    def setUp(self):
        self.user = make_user('254700000001', name='Alice Wanjiru')

    def test_renders_from_typed_params_at_read_time(self):
        a = ActivityService.record(
            actor=self.user, verb='contribution_payment',
            params={'amount': '500', 'contribution_title': 'Chama Pool'},
        )
        # Rendered fresh from verb + params, not a frozen string.
        self.assertEqual(render_activity(a), "Alice Wanjiru contributed KES 500 to Chama Pool")

    def test_render_reflects_current_actor_name(self):
        a = ActivityService.record(
            actor=self.user, verb='community_created',
            params={'community_name': 'Chama'},
        )
        self.user.name = 'Alice Mwangi'
        self.user.save(update_fields=['name'])
        a.refresh_from_db()
        # Name is live, not frozen at write time.
        self.assertEqual(render_activity(a), "Alice Mwangi created community 'Chama'")

    def test_amount_param_formatted_without_decimals(self):
        a = ActivityService.record(
            actor=self.user, verb='welfare_contribution', params={'amount': '1500.50'},
        )
        self.assertEqual(render_activity(a), "Alice Wanjiru contributed KES 1,500 to welfare fund")

    def test_unknown_verb_falls_back_to_stored_message(self):
        a = ActivityService.record(
            actor=self.user, verb='payment_made', message='Custom legacy text',
        )
        self.assertEqual(render_activity(a), 'Custom legacy text')

    def test_log_activity_shim_still_works(self):
        a = ActivityService.log_activity(self.user, 'payment_made', 'Old-style message')
        self.assertEqual(a.params, {})
        self.assertEqual(a.visibility, Activity.Visibility.PRIVATE)
        self.assertEqual(render_activity(a), 'Old-style message')


class ActivityVisibilityTests(APITestCase):
    def setUp(self):
        self.tenant   = Tenant.objects.create(slug='org', name='Org')
        self.actor    = make_user('254700000001', name='Actor')
        self.member   = make_user('254700000002', name='Member')
        self.outsider = make_user('254700000003', name='Outsider')
        self.community = Community.objects.create(name='Chama', created_by=self.actor, tenant=self.tenant)
        for u in (self.actor, self.member):
            CommunityMembership.objects.create(user=u, community=self.community, role='member')

    def test_visible_to_includes_actor_own_private_rows(self):
        a = ActivityService.record(actor=self.actor, verb='contribution_payment',
                                   params={'amount': '1', 'contribution_title': 'X'})
        self.assertIn(a, Activity.objects.visible_to(self.actor))
        self.assertNotIn(a, Activity.objects.visible_to(self.member))

    def test_community_row_visible_to_members_only(self):
        a = ActivityService.record(
            actor=self.actor, verb='community_created',
            params={'community_name': 'Chama'},
            visibility=Activity.Visibility.COMMUNITY, community=self.community,
        )
        self.assertIn(a, Activity.objects.visible_to(self.actor))
        self.assertIn(a, Activity.objects.visible_to(self.member))
        self.assertNotIn(a, Activity.objects.visible_to(self.outsider))

    def test_public_row_visible_to_all(self):
        a = ActivityService.record(actor=self.actor, verb='payment_made',
                                   message='public', visibility=Activity.Visibility.PUBLIC)
        self.assertIn(a, Activity.objects.visible_to(self.outsider))

    def test_public_row_is_tenant_scoped(self):
        # A public row belonging to another institution's tenant must never
        # surface in this viewer's feed (ADR-0008 — no cross-tenant leak).
        other_tenant = Tenant.objects.create(slug='other-org', name='Other Org')
        a = ActivityService.record(actor=self.actor, verb='payment_made',
                                   message='public', visibility=Activity.Visibility.PUBLIC)
        Activity.objects.filter(pk=a.pk).update(tenant=other_tenant)
        self.assertNotIn(a, Activity.objects.visible_to(self.outsider))


class ActivityFeedEndpointTests(APITestCase):
    def setUp(self):
        self.tenant = Tenant.objects.create(slug='org', name='Org')
        self.user   = make_user('254700000001', name='Alice')
        self.member = make_user('254700000002', name='Bob')
        self.community = Community.objects.create(name='Chama', created_by=self.user, tenant=self.tenant)
        for u in (self.user, self.member):
            CommunityMembership.objects.create(user=u, community=self.community, role='member')

    def test_personal_feed_returns_own_activity_personalized(self):
        ActivityService.record(actor=self.user, verb='contribution_payment',
                               params={'amount': '500', 'contribution_title': 'Pool'})
        resp = active_client(self.user).get('/api/activity/')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)
        # Actor's own message is personalized to "You".
        self.assertEqual(resp.data['results'][0]['message'], 'You contributed KES 500 to Pool')

    def test_personal_feed_excludes_other_users(self):
        ActivityService.record(actor=self.member, verb='contribution_payment',
                               params={'amount': '9', 'contribution_title': 'Pool'})
        resp = active_client(self.user).get('/api/activity/')
        self.assertEqual(resp.data['results'], [])

    def test_community_feed_visible_to_member(self):
        ActivityService.record(actor=self.user, verb='community_created',
                               params={'community_name': 'Chama'},
                               visibility=Activity.Visibility.COMMUNITY, community=self.community)
        resp = active_client(self.member).get(f'/api/activity/?community={self.community.id}')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 1)
        # Not the viewer's own row → rendered third-person, not "You".
        self.assertEqual(resp.data['results'][0]['message'], "Alice created community 'Chama'")

    def test_community_feed_denies_non_member(self):
        outsider = make_user('254700000009', name='Eve')
        ActivityService.record(actor=self.user, verb='community_created',
                               params={'community_name': 'Chama'},
                               visibility=Activity.Visibility.COMMUNITY, community=self.community)
        resp = active_client(outsider).get(f'/api/activity/?community={self.community.id}')
        self.assertEqual(resp.data['results'], [])

    def test_legacy_feed_shape_is_preserved(self):
        # /api/activity/ (and /api/v1/) keep the offset shape shipped mobile
        # binaries depend on: {count, results, has_more}, no cursor envelope.
        for i in range(3):
            ActivityService.record(actor=self.user, verb='payment_made', message=f'm{i}')
        resp = active_client(self.user).get('/api/activity/?limit=2&offset=0')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.data['count'], 3)
        self.assertEqual(len(resp.data['results']), 2)
        self.assertTrue(resp.data['has_more'])
        self.assertNotIn('next', resp.data)

    def test_v2_feed_is_cursor_paginated(self):
        # The cursor shape lives on /api/v2/ only (ADR-0021): {next, results}, no count.
        for i in range(3):
            ActivityService.record(actor=self.user, verb='payment_made', message=f'm{i}')
        resp = active_client(self.user).get('/api/v2/activity/?page_size=2')
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.data['results']), 2)
        self.assertIsNotNone(resp.data['next'])
        self.assertNotIn('count', resp.data)  # cursor pagination: no total-count leak
