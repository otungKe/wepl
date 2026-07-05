"""Create/refresh the Back Office ops roles as Django Groups (``ops:<role>``).

Idempotent — safe to run on every deploy. The capability mapping lives in code
(``capabilities.ROLE_CAPABILITIES``); these Groups are only the assignment handle,
so operators can be added to roles from the Django admin without touching code.
"""
from django.contrib.auth.models import Group
from django.core.management.base import BaseCommand

from apps.backoffice.capabilities import ALL_ROLES, ROLE_CAPABILITIES, group_name


class Command(BaseCommand):
    help = "Create/refresh Back Office ops roles (Django Groups)."

    def handle(self, *args, **options):
        for role in ALL_ROLES:
            name = group_name(role)
            _, created = Group.objects.get_or_create(name=name)
            caps = len(ROLE_CAPABILITIES.get(role, set()))
            self.stdout.write(
                self.style.SUCCESS(f"{'created' if created else 'ok     '} {name}  ({caps} capabilities)")
            )
        self.stdout.write(self.style.SUCCESS(f"Seeded {len(ALL_ROLES)} ops role(s)."))
