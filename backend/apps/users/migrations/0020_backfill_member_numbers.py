"""Backfill a unique member_number for every existing user."""
from django.db import migrations


def _alphabet():
    return "23456789ABCDEFGHJKMNPQRSTVWXYZ"


def backfill(apps, schema_editor):
    import secrets
    User = apps.get_model("users", "User")
    alphabet = _alphabet()
    taken = set(
        User.objects.exclude(member_number__isnull=True)
        .values_list("member_number", flat=True))

    def fresh():
        while True:
            candidate = "WM-" + "".join(secrets.choice(alphabet) for _ in range(5))
            if candidate not in taken:
                taken.add(candidate)
                return candidate

    for user in User.objects.filter(member_number__isnull=True).iterator():
        user.member_number = fresh()
        user.save(update_fields=["member_number"])


def noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):
    dependencies = [("users", "0019_user_member_number")]
    operations = [migrations.RunPython(backfill, noop)]
