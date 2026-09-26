"""Tests for the production boot guards (C-2 media durability)."""
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase

from apps.core.deploy_checks import check_durable_media, check_s3_credentials


class DurableMediaGuardTests(SimpleTestCase):
    def test_boots_when_s3_enabled(self):
        check_durable_media(debug=False, use_s3=True, allow_ephemeral=False)  # no raise

    def test_boots_in_debug(self):
        check_durable_media(debug=True, use_s3=False, allow_ephemeral=False)  # no raise

    def test_boots_with_explicit_escape_hatch(self):
        check_durable_media(debug=False, use_s3=False, allow_ephemeral=True)  # no raise

    def test_refuses_ephemeral_media_in_production(self):
        with self.assertRaises(ImproperlyConfigured):
            check_durable_media(debug=False, use_s3=False, allow_ephemeral=False)


class S3CredentialGuardTests(SimpleTestCase):
    def test_noop_when_s3_disabled(self):
        check_s3_credentials(use_s3=False, bucket='', access_key='', secret_key='')  # no raise

    def test_passes_with_full_credentials(self):
        check_s3_credentials(use_s3=True, bucket='b', access_key='k', secret_key='s')  # no raise

    def test_raises_and_names_missing_credentials(self):
        with self.assertRaises(ImproperlyConfigured) as ctx:
            check_s3_credentials(use_s3=True, bucket='b', access_key='', secret_key='')
        msg = str(ctx.exception)
        self.assertIn('AWS_ACCESS_KEY_ID', msg)
        self.assertIn('AWS_SECRET_ACCESS_KEY', msg)
        self.assertNotIn('AWS_STORAGE_BUCKET_NAME', msg)


class CallbackAllowlistGuardTests(SimpleTestCase):
    LIVE = 'https://api.safaricom.co.ke'
    SANDBOX = 'https://sandbox.safaricom.co.ke'

    def test_live_daraja_with_empty_allowlist_refuses_to_boot(self):
        with self.assertRaises(ImproperlyConfigured):
            from apps.core.deploy_checks import check_callback_allowlist
            check_callback_allowlist(mpesa_base_url=self.LIVE, allowlist=[])

    def test_live_daraja_with_allowlist_boots(self):
        from apps.core.deploy_checks import check_callback_allowlist
        check_callback_allowlist(mpesa_base_url=self.LIVE, allowlist=['196.201.214.0/24'])

    def test_sandbox_boots_with_empty_allowlist(self):
        from apps.core.deploy_checks import check_callback_allowlist
        check_callback_allowlist(mpesa_base_url=self.SANDBOX, allowlist=[])

    def test_malformed_entry_refuses_to_boot_even_on_sandbox(self):
        from apps.core.deploy_checks import check_callback_allowlist
        with self.assertRaises(ImproperlyConfigured):
            check_callback_allowlist(mpesa_base_url=self.SANDBOX, allowlist=['196.201.214.x'])


class ClientIpTests(SimpleTestCase):
    def _ip(self, xff=None, remote=None):
        from django.test import RequestFactory
        from apps.core.client_ip import client_ip
        meta = {}
        if xff is not None:
            meta['HTTP_X_FORWARDED_FOR'] = xff
        if remote is not None:
            meta['REMOTE_ADDR'] = remote
        return client_ip(RequestFactory().get('/', **meta))

    def test_first_forwarded_entry(self):
        self.assertEqual(self._ip('41.90.1.2, 10.0.0.1', '10.0.0.2'), '41.90.1.2')

    def test_garbage_forwarded_entry_falls_back_to_socket(self):
        self.assertEqual(self._ip('not-an-ip', '10.0.0.2'), '10.0.0.2')

    def test_nothing_usable_is_none(self):
        self.assertIsNone(self._ip("'; drop", 'nonsense'))
