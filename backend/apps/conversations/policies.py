"""Conversation & message authorization policy (ADR-0009).

Replaces the inline ``CommunityMembership.objects.filter(...)`` / ``created_by ==``
checks that were duplicated across ``conversations/views.py`` and ``services.py``.
Community-membership and community-admin decisions are delegated to the
``community`` policy so there is one definition of each:

  * a *community member* is ``community.view`` (creator or active member),
  * a *community admin* is ``community.update`` (creator or admin — treasurers
    excluded, matching the historical ``role='admin'`` message-moderation rule).

Actions
-------
``conversation.view``    community member may read the conversation.
``conversation.delete``  the conversation's creator OR a community admin.
``message.edit``         the message's sender only.
``message.delete``       the message's sender OR a community admin.
"""
from apps.core.policy import can, policy


@policy("conversation")
def _resolve_conversation(actor, action: str, conversation) -> bool:
    community = conversation.community
    if action == "conversation.view":
        return can(actor, "community.view", community)
    if action == "conversation.delete":
        return conversation.created_by_id == actor.id or can(actor, "community.update", community)
    raise KeyError(f"Unknown conversation action '{action}'.")


@policy("message")
def _resolve_message(actor, action: str, message) -> bool:
    if action == "message.edit":
        return message.sender_id == actor.id
    if action == "message.delete":
        return (
            message.sender_id == actor.id
            or can(actor, "community.update", message.conversation.community)
        )
    raise KeyError(f"Unknown message action '{action}'.")
