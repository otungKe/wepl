"""The activity feed written from outbox facts (ADR-0016, ADR-0029, ADR-0033).

Communities and contributions announce what happened; the feed consumer turns
each fact into a row. These tests hold the three things that can silently go
wrong with that: the consumer not being registered (the feed just stops), a
redelivered fact writing a second row, and a fact reaching the feed with the
wrong visibility.
"""
from django.test import TestCase, override_settings

from apps.communities.models import CommunityMembership
from apps.communities.services import CommunityService
from apps.core.events import emit_event, inline_consumers_for
from apps.core.models import OutboxDelivery, OutboxEvent
from apps.core.tasks import process_inline_deliveries
from apps.users.models import User

from .consumers import CONSUMER_NAME, EVENT_TYPES, _rules, record_from_event
from .models import Activity


@override_settings(ACCESS_TIER_ENFORCEMENT=False)
class ActivityConsumerTests(TestCase):
    def setUp(self):
        self.owner = User.objects.create(phone_number="254700000901", name="Achieng Otieno")
        self.member = User.objects.create(phone_number="254700000902", name="Brian Kamau")

    def test_consumer_is_registered_for_every_fact_it_has_a_rule_for(self):
        self.assertEqual(EVENT_TYPES, frozenset(_rules()))
        for event_type in EVENT_TYPES:
            names = [c.name for c in inline_consumers_for(event_type)]
            self.assertIn(CONSUMER_NAME, names, event_type)

    def test_creating_a_community_reaches_the_feed_through_the_outbox(self):
        community = CommunityService.create_community(self.owner, {"name": "Umoja"})
        # The service writes no feed row itself: the fact waits in the outbox.
        self.assertFalse(Activity.objects.filter(activity_type="community_created").exists())
        event = OutboxEvent.objects.get(event_type="community.created")
        self.assertTrue(OutboxDelivery.objects.filter(
            outbox_event=event, consumer_name=CONSUMER_NAME).exists())

        process_inline_deliveries(outbox_event_id=event.id)

        row = Activity.objects.get(activity_type="community_created")
        self.assertEqual(row.user, self.owner)
        self.assertEqual(row.community, community)
        self.assertEqual(row.visibility, Activity.Visibility.COMMUNITY)
        self.assertEqual(row.source_event_id, event.id)
        self.assertIn("Umoja", row.message)

    def test_joining_and_leaving_are_announced(self):
        community = CommunityService.create_community(self.owner, {"name": "Umoja"})
        CommunityService.join_community(self.member, community)
        CommunityService.leave_community(self.member, community)
        process_inline_deliveries()

        joined = Activity.objects.get(activity_type="community_joined")
        self.assertEqual(joined.community, community)
        left = Activity.objects.get(activity_type="community_left")
        # Leaving is the member's own business: private, and not community-scoped.
        self.assertEqual(left.visibility, Activity.Visibility.PRIVATE)
        self.assertIsNone(left.community)
        self.assertFalse(CommunityMembership.objects.filter(
            user=self.member, community=community, is_active=True).exists())

    def test_a_redelivered_fact_writes_one_row(self):
        event = emit_event("welfare.contributed", body={
            "actor_id": self.member.pk, "welfare_fund_id": 1, "amount": "500"})
        record_from_event(event)
        record_from_event(event)
        self.assertEqual(Activity.objects.filter(source_event_id=event.id).count(), 1)

    def test_money_facts_are_private_even_when_they_name_a_community(self):
        event = emit_event("contribution.paid", body={
            "actor_id": self.member.pk, "contribution_id": 7,
            "contribution_title": "School fees", "amount": "1500",
            "community_id": 99})
        record_from_event(event)
        row = Activity.objects.get(source_event_id=event.id)
        self.assertEqual(row.visibility, Activity.Visibility.PRIVATE)
        self.assertIsNone(row.community)
        self.assertEqual(row.params, {"amount": "1500", "contribution_title": "School fees"})

    def test_a_fact_for_a_deleted_actor_is_dropped_not_retried(self):
        event = emit_event("standing_order.executed", body={
            "actor_id": 999999, "standing_order_id": 1, "amount": "100",
            "recipient": "254700000000"})
        record_from_event(event)
        self.assertFalse(Activity.objects.filter(source_event_id=event.id).exists())
