from .models import Activity
from .render import render_activity


class ActivityService:
    @staticmethod
    def record(actor, verb, *, params=None, message=None,
               visibility=Activity.Visibility.PRIVATE, community=None,
               source_event_id=None):
        """
        Record a typed activity event (ADR-0016).

        actor      — the user who performed the action.
        verb       — the activity_type (e.g. 'contribution_payment').
        params     — JSON-serialisable primitives used to render the message at
                     read time (e.g. {'amount': '500', 'contribution_title': 'X'}).
        message    — optional pre-rendered fallback; if omitted it is derived from
                     verb + params and stored as the render cache.
        visibility — 'private' (actor only), 'community', or 'public'.
        community  — scope for community-visible rows (required for 'community').
        source_event_id — the outbox fact this row came from, when it came
                     from one (see ``consumers``); unique, so a redelivered
                     fact cannot write a second row.
        """
        from apps.tenants.resolve import tenant_for_user

        params = params or {}
        # Stamp the owning tenant (ADR-0008): the community's tenant when scoped
        # to one, else the actor's — so public rows are tenant-isolated at read.
        tenant = getattr(community, 'tenant', None) or tenant_for_user(actor)
        activity = Activity(
            user=actor,
            activity_type=verb,
            params=params,
            visibility=visibility,
            community=community,
            tenant=tenant,
            source_event_id=source_event_id,
        )
        # Store a rendered fallback (search target + back-compat for old clients).
        activity.message = message if message is not None else render_activity(activity)
        activity.save()
        return activity

    @staticmethod
    def log_activity(user, activity_type, message):
        """Back-compat shim (pre-ADR-0016 callers). Stores the pre-rendered
        string with empty params and private visibility."""
        return ActivityService.record(
            actor=user, verb=activity_type, message=message,
        )
