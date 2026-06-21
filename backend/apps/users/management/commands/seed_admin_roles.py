"""Seed scoped admin roles (Django Groups) for platform staff.

Lets you delegate the Django admin without handing out superuser. Assign a staff
user (is_staff=True) to one or more of these groups in /admin/ → Users.

    python manage.py seed_admin_roles

Roles (model → allowed actions):
  • KYC Reviewers        — review/approve/reject KYC; read users.
  • Support              — read users, KYC, communities (triage, no money).
  • Finance & Compliance — read the ledger, transactions, M-Pesa (read-only;
                           the ledger is immutable — money moves only via
                           post_journal(), never the admin).

Re-running is safe: it creates missing groups and re-applies their permission
sets idempotently.
"""
from django.contrib.auth.models import Group, Permission
from django.core.management.base import BaseCommand

# group name → list of (app_label, model_name, [actions])
ROLES: dict[str, list[tuple[str, str, list[str]]]] = {
    'KYC Reviewers': [
        ('users', 'kycprofile', ['view', 'change']),
        ('users', 'user',       ['view']),
    ],
    'Support': [
        ('users',       'user',                 ['view']),
        ('users',       'kycprofile',           ['view']),
        ('communities', 'community',            ['view']),
        ('communities', 'communitymembership',  ['view']),
        ('communities', 'communityjoinrequest', ['view']),
    ],
    'Finance & Compliance': [
        ('ledger',        'journalentry',         ['view']),
        ('ledger',        'journalline',          ['view']),
        ('ledger',        'account',              ['view']),
        ('ledger',        'accountbalance',       ['view']),
        ('ledger',        'financialtransaction', ['view']),
        ('contributions', 'contributiontransaction', ['view']),
        ('mpesa',         'mpesac2btransaction',  ['view']),
        ('mpesa',         'mpesastkrequest',      ['view']),
    ],
}


class Command(BaseCommand):
    help = 'Create/refresh scoped admin roles (Groups) for platform staff.'

    def handle(self, *args, **options):
        for group_name, specs in ROLES.items():
            group, created = Group.objects.get_or_create(name=group_name)
            perms = []
            for app_label, model, actions in specs:
                for action in actions:
                    codename = f'{action}_{model}'
                    try:
                        perms.append(Permission.objects.get(
                            content_type__app_label=app_label,
                            codename=codename,
                        ))
                    except Permission.DoesNotExist:
                        self.stderr.write(self.style.WARNING(
                            f"  ! permission {app_label}.{codename} not found — skipped"
                        ))
            group.permissions.set(perms)
            verb = 'Created' if created else 'Updated'
            self.stdout.write(self.style.SUCCESS(
                f"{verb} role '{group_name}' with {len(perms)} permission(s)."
            ))

        self.stdout.write(
            "\nAssign staff to a role in /admin/ → Users (set is_staff=True, "
            "then add the group). Superusers keep full access."
        )
