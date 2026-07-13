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


class Program(models.Model):
    """A named financial arrangement an Organization operates (ADR-0026).

    The registry spine over the three fund models — `Contribution`,
    `WelfareFund`, `SharesFund` are its first archetype *profiles* (the same
    spine + profile pattern as Organization/Community). The ledger's
    ``(fund_type, fund_id)`` account anchoring is untouched; Program generalizes
    ``fund_type`` from enum to entity so new surfaces (catalogue, subscriptions,
    ops) enumerate one concept.

    Thin by design: terms/lifecycle stay on the profile models until a second
    program archetype needs them up here. Subscription (the org↔program edge
    that replaces "Provider") arrives in Phase 1.
    """

    class ProgramType(models.TextChoices):
        # Mirrors the ledger's fund_type vocabulary (coa._FUND_GL). 'advance'
        # is deliberately absent: a per-member receivable is not a program a
        # member subscribes to — a Loan Facility program arrives with Phase 2.
        CONTRIBUTION = 'contribution', 'Contribution / Pool'
        WELFARE      = 'welfare',      'Welfare Fund'
        SHARES       = 'shares',       'Shares Fund'

    uid          = models.UUIDField(unique=True, editable=False)
    name         = models.CharField(max_length=255)
    program_type = models.CharField(max_length=30, choices=ProgramType.choices)

    # The operating organization. Null for personal/open pools that belong to no
    # organization yet (a standalone contribution created by an individual).
    organization = models.ForeignKey(
        Organization, null=True, blank=True,
        on_delete=models.PROTECT, related_name='programs',
    )
    # Hosting boundary (RLS parity, C-1) — inherited from the operating org's
    # community; null = platform/shared.
    tenant = models.ForeignKey(
        'tenants.Tenant', null=True, blank=True,
        on_delete=models.PROTECT, related_name='programs',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ('name',)
        indexes = [
            models.Index(fields=['program_type'], name='program_type_idx'),
            models.Index(fields=['organization'], name='program_org_idx'),
        ]

    def save(self, *args, **kwargs):
        if not self.uid:
            self.uid = uuid7()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} [{self.program_type}]"


def ensure_program(*, fund, program_type: str) -> Program:
    """Idempotently resolve the Program spine row for a fund profile.

    The single sanctioned way a fund acquires its Program — used by the three
    creation paths and the backfill so all produce identical rows. Duck-typed
    over the fund profiles (Contribution has ``title``; the others ``name``;
    all have an optional ``community``) so this spine app never imports
    contributions models.
    """
    if fund.program_id:
        return fund.program
    community = getattr(fund, 'community', None)
    organization = (community.organization
                    if community is not None and community.organization_id else None)
    program = Program.objects.create(
        name=getattr(fund, 'title', None) or getattr(fund, 'name', '') or '',
        program_type=program_type,
        organization=organization,
        tenant_id=community.tenant_id if community is not None else None,
    )
    fund.program = program
    fund.save(update_fields=['program'])
    return program


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
