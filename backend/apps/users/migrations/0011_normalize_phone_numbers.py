"""Canonicalise existing user phone numbers to 2547XXXXXXXX.

Auth views used to store the phone exactly as the client sent it, so the table
may contain a mix of 0712…, 712…, +254712… and 254712… for what is logically
the same MSISDN. Going forward the views normalise on the way in; this backfills
the rows that already exist so those accounts can log in from any client.
"""
import re

from django.db import migrations


def _normalize(raw):
    if not raw:
        return ""
    digits = re.sub(r"\D", "", raw)
    if digits.startswith("0"):
        return "254" + digits[1:]
    if digits.startswith("7") or digits.startswith("1"):
        return "254" + digits
    return digits


def forwards(apps, schema_editor):
    User = apps.get_model("users", "User")
    taken = set(User.objects.values_list("phone_number", flat=True))
    for user in User.objects.all().iterator():
        canon = _normalize(user.phone_number)
        if not canon or canon == user.phone_number:
            continue
        # Don't collide with a row that already holds the canonical form.
        if canon in taken:
            continue
        taken.discard(user.phone_number)
        taken.add(canon)
        user.phone_number = canon
        user.save(update_fields=["phone_number"])


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0010_user_last_seen"),
    ]

    operations = [
        migrations.RunPython(forwards, migrations.RunPython.noop),
    ]
