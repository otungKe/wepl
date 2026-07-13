"""Organization — the participant spine (ADR-0026, Phase 0).

Every participant on the platform is an Organization: a chama, a SACCO, a
church, a wealth manager are the same thing at different scales — an
organization with members, money, and rules. `Community` is the first
*archetype*: the Organization row is the general spine; the Community row is its
archetype-specific profile (the spine + profile pattern).

Deliberately thin. Fields migrate up from Community only when a second archetype
actually needs them (rule of three). Archetype is metadata, not taxonomy — no
`if org.archetype == …` branches belong in domain logic; archetypes select
capability bundles and governance profiles (later phases).
"""
from django.db import models

from apps.core.ids import uuid7


class Organization(models.Model):
    """The general participant entity. See module docstring and ADR-0026."""

    class Archetype(models.TextChoices):
        # Archetypes are EARNED, not designed upfront (strategy doc §4, §10).
        # New members of this enum arrive with a real customer segment, a
        # capability bundle, and a governance profile — not before.
        COMMUNITY = 'community', 'Community'

    # External, opaque, stable handle (UUIDv7 — same identity philosophy as
    # ledger Account.account_uid, ADR-0025). Internal joins use the bigint pk.
    uid = models.UUIDField(unique=True, editable=False)

    name      = models.CharField(max_length=255)
    archetype = models.CharField(max_length=30, choices=Archetype.choices)

    # The HOSTING/ISOLATION boundary (ADR-0008), an attribute — never a
    # hierarchy. Many light organizations (chamas) share the default tenant;
    # operational archetypes (a hosted SACCO) get a dedicated one. Null =
    # platform/shared, consistent with every other tenant-columned table.
    tenant = models.ForeignKey(
        'tenants.Tenant', null=True, blank=True,
        on_delete=models.PROTECT, related_name='organizations',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['archetype'], name='org_archetype_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid7()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.archetype}]"


def ensure_organization_for_community(community) -> Organization:
    """Idempotently resolve the Organization spine row for a community.

    The single sanctioned way a community acquires its Organization — used by
    the creation path and the backfill so both produce identical rows. Keyed on
    the community's OneToOne link (not name, which is mutable metadata).
    """
    if community.organization_id:
        return community.organization
    org = Organization.objects.create(
        name=community.name,
        archetype=Organization.Archetype.COMMUNITY,
        tenant_id=community.tenant_id,
    )
    community.organization = org
    community.save(update_fields=['organization'])
    return org
