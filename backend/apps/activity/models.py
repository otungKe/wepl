from django.conf import settings
from django.db import models


class ActivityQuerySet(models.QuerySet):
    def visible_to(self, user):
        """
        Rows the given user is allowed to see (ADR-0016 visibility rule, encoded
        once):
          - they are the actor, OR
          - the row is community-scoped and they are an active member of that
            community, OR
          - the row is public *within the viewer's tenant* (a public row from
            another institution never crosses the tenant boundary, ADR-0008).
        """
        from apps.communities.models import CommunityMembership
        from apps.tenants.resolve import tenant_for_user

        member_community_ids = CommunityMembership.objects.filter(
            user=user, is_active=True
        ).values('community_id')
        viewer_tenant_id = tenant_for_user(user).id

        return self.filter(
            models.Q(user=user)
            | models.Q(visibility=Activity.Visibility.COMMUNITY,
                       community_id__in=member_community_ids)
            | models.Q(visibility=Activity.Visibility.PUBLIC,
                       tenant_id=viewer_tenant_id)
        )


class Activity(models.Model):
    class Visibility(models.TextChoices):
        PRIVATE   = 'private',   'Private (actor only)'
        COMMUNITY = 'community', 'Community members'
        PUBLIC    = 'public',    'Public'

    ACTIVITY_TYPES = (
        ('community_created', 'Community Created'),
        ('community_joined', 'Community Joined'),
        ('community_left', 'Community Left'),
        ('community_ownership_transferred', 'Community Ownership Transferred'),
        ('conversation_created', 'Conversation Created'),
        ('message_sent', 'Message Sent'),
        ('contribution_created', 'Contribution Created'),
        ('contribution_payment', 'Contribution Payment'),
        ('standing_order_executed', 'Standing Order Executed'),
        ('welfare_contribution', 'Welfare Contribution'),
        ('payment_made', 'Payment Made'),
    )

    # The actor — the user who performed the action (and the owner of the
    # personal feed). Kept named `user` for back-compat; `actor` is an alias.
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE
    )

    activity_type = models.CharField(
        max_length=50,
        choices=ACTIVITY_TYPES
    )

    # Typed-event params (JSON primitives) used to render the message at read
    # time (ADR-0016). `message` is the denormalized render cache / fallback for
    # old rows and unknown verbs — intentionally retained, never authoritative.
    params = models.JSONField(default=dict, blank=True)

    message = models.TextField()

    # Who may see this row. Defaults to private (actor-only), preserving the
    # original personal-feed behaviour.
    visibility = models.CharField(
        max_length=16,
        choices=Visibility.choices,
        default=Visibility.PRIVATE,
    )

    # Scope for community-visible activity (null for personal/public rows).
    community = models.ForeignKey(
        'communities.Community',
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name='activities',
    )

    # Owning tenant (ADR-0008). Stamped on write from the community, else the
    # actor's tenant. Used to scope *public* rows so a public activity from one
    # institution can never surface in another tenant's feed. Null = legacy/shared.
    tenant = models.ForeignKey(
        'tenants.Tenant',
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name='+',
    )

    created_at = models.DateTimeField(auto_now_add=True)

    objects = ActivityQuerySet.as_manager()

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['user', '-created_at'], name='activity_user_date_idx'),
            models.Index(fields=['community', '-created_at'], name='activity_comm_date_idx'),
        ]

    def __str__(self):
        return self.render()

    @property
    def actor(self):
        return self.user

    def render(self):
        """Render the human sentence from verb + params at read time, falling
        back to the stored `message` for old rows / unknown verbs."""
        from .render import render_activity
        return render_activity(self)
