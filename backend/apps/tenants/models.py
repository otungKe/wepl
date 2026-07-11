"""
Tenant — the multi-tenancy boundary (ADR-0008).

A Tenant is one hosted institution (a SACCO, an enterprise group, a future BaaS
client). The business root for a tenant is the Community; financial data
(Account / FinancialTransaction / journals) carries a ``tenant`` FK so reporting
and isolation can be scoped per tenant. A null tenant means platform/shared
(e.g. global GL accounts).
"""
from django.db import models

DEFAULT_TENANT_SLUG = 'default'


class Tenant(models.Model):
    name       = models.CharField(max_length=120)
    slug       = models.SlugField(max_length=60, unique=True)
    is_active  = models.BooleanField(default=True)
    # Free-form per-tenant configuration (limits, branding, presentation
    # currency, …). Kept as JSON so config is additive without migrations.
    config     = models.JSONField(default=dict, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)

    def __str__(self):
        return f"{self.name} ({self.slug})"


class CrossTenantAccessAttempt(models.Model):
    """Audit of a blocked cross-tenant access.

    Recorded by ``apps.tenants.guards.guard_tenant`` when a request pinned to one
    tenant tries to reach a resource owned by another. RLS already blocks the
    ledger tables at the DB; this guard + audit covers app-level access to
    tenant-owned aggregates (communities, funds) and gives a queryable trail.
    """
    created_at      = models.DateTimeField(auto_now_add=True, db_index=True)
    user            = models.ForeignKey(
        'users.User', null=True, blank=True, on_delete=models.SET_NULL,
        related_name='cross_tenant_attempts',
    )
    current_tenant  = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    resource_tenant = models.ForeignKey(
        Tenant, null=True, blank=True, on_delete=models.SET_NULL, related_name='+',
    )
    resource_type   = models.CharField(max_length=60, blank=True)
    resource_id     = models.CharField(max_length=64, blank=True)
    path            = models.CharField(max_length=255, blank=True)

    class Meta:
        ordering = ('-created_at',)
        indexes = [models.Index(fields=['created_at'], name='xtenant_created_idx')]

    def __str__(self):
        return f"cross-tenant {self.resource_type}#{self.resource_id} by user {self.user_id}"
