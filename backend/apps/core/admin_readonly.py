"""Read-only Django admin for records that only a controlled command may change.

Django admin sits outside the ops console's capabilities, step-up, maker-checker
and audit trail (ADR-0019, backoffice/capabilities.py), and a Django superuser is
not a financial authority. So for money, controls and rail records the admin is a
viewer: no add, no change, no delete. Changes go through the owning service —
``post_journal()``, ``transition_to()``, the ops console — never a form.
"""


class ReadOnlyAdminMixin:
    """Mix into a ``ModelAdmin`` (or inline) to make it view-only."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
