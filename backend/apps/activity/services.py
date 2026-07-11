from .models import Activity
from .render import render_activity


class ActivityService:
    @staticmethod
    def record(actor, verb, *, params=None, message=None,
               visibility=Activity.Visibility.PRIVATE, community=None):
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
        """
        params = params or {}
        activity = Activity(
            user=actor,
            activity_type=verb,
            params=params,
            visibility=visibility,
            community=community,
        )
        # Store a rendered fallback (search target + back-compat for old clients).
        activity.message = message if message is not None else render_activity(activity)
        activity.save()
        return activity

    @staticmethod
    def log_activity(user, activity_type, message):
        """Back-compat shim (ADR-0016). Stores the pre-rendered
        string with empty params and private visibility."""
        return ActivityService.record(
            actor=user, verb=activity_type, message=message,
        )
