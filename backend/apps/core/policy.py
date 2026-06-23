"""Centralized authorization policy layer (ADR-0009).

Fine-grained authorization ("may *this* actor perform *this* action on *this*
resource") used to live as inline role checks scattered across views and
services. This module makes it a single, declarative, testable system.

Usage
-----
At the HTTP/service boundary, gate an action::

    from apps.core.policy import require
    require(request.user, "community.update", community)   # raises 403 if denied

Branch without raising (serializers, conditional UI fields)::

    from apps.core.policy import can
    if can(request.user, "community.members.view_all", community):
        ...

Registering a resource's rules
------------------------------
Each resource type registers exactly one resolver, keyed by the *prefix* of the
action string (the part before the first ``.``)::

    from apps.core.policy import policy

    @policy("community")
    def _resolve(actor, action, community) -> bool:
        ...

Resolvers must be imported at startup so they register — do it in the app's
``AppConfig.ready()``.

Design notes
------------
- Raises Django's ``PermissionDenied`` (not DRF's) so the layer is free of HTTP
  coupling and usable from services, Celery tasks and WebSocket consumers. The
  project's ``core.exceptions.custom_exception_handler`` maps it to a clean 403.
- Superusers bypass (platform operators). Unauthenticated actors are always denied.
- The action namespace convention is ``"<resource_type>.<area>.<verb>"`` — only
  the first segment selects the resolver; the rest is the resolver's concern.
"""
import logging
from typing import Callable

from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

# action-prefix -> resolver(actor, action, resource) -> bool
Resolver = Callable[[object, str, object], bool]
_RESOLVERS: dict[str, Resolver] = {}


class PolicyConfigurationError(RuntimeError):
    """Raised when an action has no registered resolver — a wiring bug, not an
    authz decision. Surfacing it loudly prevents 'fail-open' on a typo."""


def policy(resource_type: str) -> Callable[[Resolver], Resolver]:
    """Register the resolver for every action prefixed ``"<resource_type>."``."""
    def decorator(fn: Resolver) -> Resolver:
        if resource_type in _RESOLVERS:
            logger.warning("Policy resolver for '%s' is being overwritten.", resource_type)
        _RESOLVERS[resource_type] = fn
        return fn
    return decorator


def _resolver_for(action: str) -> Resolver:
    prefix = action.split(".", 1)[0]
    resolver = _RESOLVERS.get(prefix)
    if resolver is None:
        raise PolicyConfigurationError(
            f"No authorization policy registered for resource '{prefix}' "
            f"(action '{action}'). Did the app's AppConfig.ready() import its policies?"
        )
    return resolver


def can(actor, action: str, resource) -> bool:
    """Return whether *actor* may perform *action* on *resource*. Never raises an
    authz error (a missing resolver still raises, as that's a config bug)."""
    if actor is None or not getattr(actor, "is_authenticated", False):
        return False
    if getattr(actor, "is_superuser", False):
        return True
    return bool(_resolver_for(action)(actor, action, resource))


def require(actor, action: str, resource, message: str | None = None) -> None:
    """Enforce *action*; raise ``PermissionDenied`` (→ 403) when denied."""
    if not can(actor, action, resource):
        raise PermissionDenied(message or "You do not have permission to perform this action.")
