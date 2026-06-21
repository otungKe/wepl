"""Create or update a superuser non-interactively from environment variables.

Runs on every deploy (from start.sh) so the platform admin exists without shell
access (Render's free tier has none). Set these on the service:

    ADMIN_PHONE     — login phone number (the USERNAME_FIELD), e.g. 254712345678
    ADMIN_PASSWORD  — admin password for /admin/ (separate from the app PIN)

Idempotent: re-running ensures the account is a superuser and that its password
matches ADMIN_PASSWORD (so rotating the env var rotates the password). If either
var is unset it skips quietly — deploys never fail because of this.
"""
import os

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = 'Create/update the platform superuser from ADMIN_PHONE / ADMIN_PASSWORD.'

    def handle(self, *args, **options):
        phone = os.environ.get('ADMIN_PHONE', '').strip()
        password = os.environ.get('ADMIN_PASSWORD', '')

        if not phone or not password:
            self.stdout.write('ensure_superuser: ADMIN_PHONE/ADMIN_PASSWORD not set — skipping.')
            return

        User = get_user_model()
        user, created = User.objects.get_or_create(phone_number=phone)
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.is_phone_verified = True
        user.set_password(password)
        user.save()

        self.stdout.write(self.style.SUCCESS(
            f"ensure_superuser: {'created' if created else 'updated'} superuser {phone}."
        ))
