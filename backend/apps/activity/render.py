"""
Read-time rendering of activity rows from typed (verb + params) events.

ADR-0016: activity is stored as a verb (`activity_type`) plus JSON `params`;
the human sentence is produced here at read time, not frozen at write time.
Each renderer takes the actor's display name and the row's params and returns a
third-person sentence. The view personalizes (actor → "You") for the actor's own
feed. Unknown verbs / empty params fall back to the stored `message`.

English-only for now; render-at-read makes a locale catalogue a drop-in later.
"""
from decimal import Decimal, InvalidOperation


def _amount(params):
    """Format a KES amount param without trailing decimals (e.g. '500' → KES 500).

    Money is Decimal, never float (CLAUDE.md — the one rule that matters). The
    amount rides in ``params`` as a string (``str(Decimal)``); parse it back as a
    Decimal for a precision-safe display format.
    """
    raw = params.get('amount')
    try:
        value = Decimal(str(raw))
    except (InvalidOperation, TypeError, ValueError):
        return f"KES {raw}"
    return f"KES {value:,.0f}"


RENDERERS = {
    'community_created':
        lambda a, p: f"{a} created community '{p.get('community_name', '')}'",
    'community_joined':
        lambda a, p: f"{a} joined '{p.get('community_name', '')}'",
    'community_left':
        lambda a, p: f"{a} left '{p.get('community_name', '')}'",
    'community_ownership_transferred':
        lambda a, p: (f"{a} transferred ownership of "
                      f"'{p.get('community_name', '')}' to {p.get('new_owner_name', '')}"),
    'contribution_created':
        lambda a, p: f"{a} created contribution '{p.get('contribution_title', '')}'",
    'contribution_payment':
        lambda a, p: (f"{a} contributed {_amount(p)} to "
                      f"{p.get('contribution_title', '')}"),
    'welfare_contribution':
        lambda a, p: f"{a} contributed {_amount(p)} to welfare fund",
    'standing_order_executed':
        lambda a, p: f"Standing order of {_amount(p)} paid to {p.get('recipient', '')}",
}


def actor_display(user):
    return (getattr(user, 'name', '') or '').strip() or user.phone_number


def render_activity(activity):
    """Render an Activity row to a sentence, falling back to the stored message."""
    renderer = RENDERERS.get(activity.activity_type)
    if renderer and activity.params:
        try:
            return renderer(actor_display(activity.user), activity.params)
        except Exception:
            pass
    return activity.message
