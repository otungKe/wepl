"""The activity feed as a consumer of domain facts (ADR-0016, ADR-0029).

Communities and contributions do not write the feed. They announce what
happened through :func:`apps.core.events.emit_event`, in the same transaction
as the change, and this module turns each fact into a feed row. Nothing imports
``apps.activity``, which is what takes it out of the import cycle (ADR-0033).

The feed decides how a fact reads and who sees it; producers only say what
happened. Money facts stay private because the amount is sensitive.
"""
from __future__ import annotations

from dataclasses import dataclass

CONSUMER_NAME = "activity.feed"


@dataclass(frozen=True)
class FeedRule:
    verb: str
    visibility: str
    params: tuple[str, ...]
    community_scoped: bool = False


def _rules():
    from .models import Activity

    community = Activity.Visibility.COMMUNITY
    private = Activity.Visibility.PRIVATE
    return {
        "community.created": FeedRule(
            "community_created", community, ("community_name",), True),
        "community.member_joined": FeedRule(
            "community_joined", community, ("community_name",), True),
        "community.member_left": FeedRule(
            "community_left", private, ("community_name",)),
        "community.ownership_transferred": FeedRule(
            "community_ownership_transferred", community,
            ("community_name", "new_owner_name"), True),
        "community.archived": FeedRule(
            "community_archived", community, ("community_name",), True),
        "contribution.created": FeedRule(
            "contribution_created", community, ("contribution_title",), True),
        "contribution.paid": FeedRule(
            "contribution_payment", private, ("amount", "contribution_title")),
        "standing_order.executed": FeedRule(
            "standing_order_executed", private, ("amount", "recipient")),
        "welfare.contributed": FeedRule(
            "welfare_contribution", private, ("amount",)),
    }


#: The facts the feed listens to. Kept as a literal so registration does not
#: need the models loaded; ``tests`` checks it matches the rules.
EVENT_TYPES = frozenset({
    "community.created", "community.member_joined", "community.member_left",
    "community.ownership_transferred", "community.archived",
    "contribution.created", "contribution.paid",
    "standing_order.executed", "welfare.contributed",
})


def record_from_event(event) -> None:
    """Write the feed row for one outbox fact. Idempotent on the event id."""
    from django.contrib.auth import get_user_model

    from apps.communities.models import Community

    from .models import Activity
    from .services import ActivityService

    if Activity.objects.filter(source_event_id=event.id).exists():
        return
    rule = _rules()[event.event_type]
    body = event.payload or {}
    actor = get_user_model().objects.filter(pk=body.get("actor_id")).first()
    if actor is None:
        # The actor was deleted before the feed caught up: there is no feed to
        # write into, and retrying will not bring them back.
        return
    community = None
    if rule.community_scoped and body.get("community_id"):
        community = Community.objects.filter(pk=body["community_id"]).first()
    ActivityService.record(
        actor=actor,
        verb=rule.verb,
        params={k: body[k] for k in rule.params if k in body},
        visibility=rule.visibility,
        community=community,
        source_event_id=event.id,
    )


def register() -> None:
    from apps.core.events import register_inline_consumer

    register_inline_consumer(CONSUMER_NAME, EVENT_TYPES, record_from_event)
