"""Tenant-scoped Channels group naming for chat.

The Channels group that fans a conversation's events out to its WebSocket
subscribers is namespaced by tenant, so groups can never collide across tenants
(or shards, should conversation ids ever stop being globally unique). Every
sender (the REST views) and the consumer derive the name here so they always
agree on it.
"""
from .models import Conversation


def group_name(tenant_id, conversation_id) -> str:
    return f"conv_{tenant_id}_{conversation_id}"


def group_for_conversation_id(conversation_id) -> str:
    """Resolve a conversation's tenant and build its group name (one indexed read)."""
    tenant_id = (
        Conversation.objects
        .filter(id=conversation_id)
        .values_list("community__tenant_id", flat=True)
        .first()
    )
    return group_name(tenant_id, conversation_id)
