"""
Tenant — the multi-tenancy boundary (Phase 6, ADR-0008).

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
