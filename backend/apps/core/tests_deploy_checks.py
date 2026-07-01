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
