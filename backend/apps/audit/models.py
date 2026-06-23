"""Append-only audit log (ADR-0019).

Records administrative / security-relevant actions that happen outside the money
ledger, so "who did this, when, from where" is queryable for compliance and
incident response. Rows are immutable: ``save()`` refuses updates and there is no
sanctioned delete path.
"""
from django.conf import settings
from django.db import models


class AuditEvent(models.Model):
    # Who. SET_NULL + a denormalised label so the trail survives account deletion
    # / anonymisation (the label is captured at write time).
    actor = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_events",
    )
    actor_label = models.CharField(max_length=120, blank=True, default="")

    # What. Dotted, namespaced action, e.g. "community.ownership_transferred".
    action = models.CharField(max_length=80, db_index=True)

    # On what. Generic target reference (no FK — targets span many models / may be gone).
    target_type = models.CharField(max_length=60, blank=True, default="")
    target_id   = models.CharField(max_length=64, blank=True, default="")

    tenant = models.ForeignKey(
        "tenants.Tenant", null=True, blank=True,
        on_delete=models.SET_NULL, related_name="audit_events",
    )

    metadata   = models.JSONField(default=dict, blank=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    request_id = models.CharField(max_length=64, blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["target_type", "target_id"], name="audit_target_idx"),
            models.Index(fields=["action", "-created_at"],     name="audit_action_idx"),
            models.Index(fields=["actor", "-created_at"],       name="audit_actor_idx"),
        ]

    def __str__(self):
        return f"{self.action} by {self.actor_label or 'system'} @ {self.created_at:%Y-%m-%d %H:%M}"

    def save(self, *args, **kwargs):
        if self.pk is not None:
            # Append-only: existing rows are immutable.
            raise ValueError("AuditEvent is append-only; existing rows cannot be modified.")
        return super().save(*args, **kwargs)
