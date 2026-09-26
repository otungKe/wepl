"""Messaging vendors stay behind ``apps.core.messaging`` (boundary audit step 7)."""
from pathlib import Path

from django.test import SimpleTestCase

APPS_DIR = Path(__file__).resolve().parent.parent
MESSAGING_DIR = APPS_DIR / "core" / "messaging"
VENDOR_MARKERS = ("africastalking", "api.brevo.com")


class MessagingPortTests(SimpleTestCase):

    def test_no_app_talks_to_a_messaging_vendor_directly(self):
        offenders = []
        for path in APPS_DIR.rglob("*.py"):
            if MESSAGING_DIR in path.parents or path.name.startswith("tests"):
                continue
            text = path.read_text(encoding="utf-8")
            offenders += [f"{path.relative_to(APPS_DIR)}: {m}"
                          for m in VENDOR_MARKERS if m in text]
        self.assertEqual(
            offenders, [],
            "Send texts and emails through apps.core.messaging "
            "(get_sms_gateway, send_email), not a vendor client.")

    def test_console_gateway_is_used_under_debug(self):
        from django.test import override_settings

        from apps.core.messaging import get_sms_gateway
        from apps.core.messaging.sms import ConsoleSMSGateway

        get_sms_gateway.cache_clear()
        try:
            with override_settings(SMS_BACKEND="", DEBUG=True):
                self.assertIsInstance(get_sms_gateway(), ConsoleSMSGateway)
        finally:
            get_sms_gateway.cache_clear()
