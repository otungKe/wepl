"""Bootstrap the first Back Office Platform Super Admin (StaffAccount) from env.

Idempotent — safe on every deploy. Reads OPS_ADMIN_EMAIL / OPS_ADMIN_PASSWORD;
skips quietly if they're unset. Creates a super_admin StaffAccount (all
capabilities) or updates the password of the existing one. Unlike normal
operators, the bootstrap admin is created with must_change_password=False so the
platform is never locked out.
"""
from django.core.management.base import BaseCommand
from decouple import config

from apps.backoffice.capabilities import group_name
from apps.backoffice.models import StaffAccount
from django.contrib.auth.models import Group


class Command(BaseCommand):
    help = "Create/update the bootstrap Back Office super admin from env vars."

    def handle(self, *args, **options):
        email = (config("OPS_ADMIN_EMAIL", default="") or "").strip().lower()
        password = config("OPS_ADMIN_PASSWORD", default="") or ""
        if not email or not password:
            self.stdout.write("OPS_ADMIN_EMAIL / OPS_ADMIN_PASSWORD not set — skipping.")
            return

        acct, created = StaffAccount.objects.get_or_create(email=email)
        acct.is_superuser = True
        acct.is_active = True
        acct.must_change_password = False
        acct.set_password(password)
        acct.save()
        g, _ = Group.objects.get_or_create(name=group_name("super_admin"))
        acct.groups.add(g)
        self.stdout.write(self.style.SUCCESS(
            f"{'Created' if created else 'Updated'} Back Office super admin {email}."))
