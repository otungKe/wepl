"""SafaricomIPPermission: who may post to the M-Pesa callback endpoints."""
from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory

from apps.mpesa.permissions import SafaricomIPPermission

RANGES = ['196.201.214.0/24', '196.201.216.200']


class SafaricomIPPermissionTests(SimpleTestCase):
    def _allowed(self, forwarded=None, remote='10.0.0.1'):
        extra = {'REMOTE_ADDR': remote}
        if forwarded is not None:
            extra['HTTP_X_FORWARDED_FOR'] = forwarded
        request = APIRequestFactory().post('/api/mpesa/stk/callback/', {}, **extra)
        return SafaricomIPPermission().has_permission(request, view=None)

    @override_settings(SAFARICOM_CALLBACK_IPS=[])
    def test_empty_allowlist_admits_everyone(self):
        self.assertTrue(self._allowed('203.0.113.9'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=1)
    def test_address_inside_a_cidr_range_is_admitted(self):
        self.assertTrue(self._allowed('196.201.214.17'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=1)
    def test_single_address_entry_is_admitted(self):
        self.assertTrue(self._allowed('196.201.216.200'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=1)
    def test_outsider_is_refused(self):
        self.assertFalse(self._allowed('203.0.113.9'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=1)
    def test_spoofed_leftmost_forwarded_entry_is_ignored(self):
        # The caller writes the left of the header; the proxy appends the real
        # sender on the right. Only the right-hand entry counts.
        self.assertFalse(self._allowed('196.201.214.17, 203.0.113.9'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=2)
    def test_hops_count_from_the_right(self):
        self.assertTrue(self._allowed('1.2.3.4, 196.201.214.17, 10.1.1.1'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=1)
    def test_missing_forwarded_header_is_refused(self):
        self.assertFalse(self._allowed(None, remote='196.201.214.17'))

    @override_settings(SAFARICOM_CALLBACK_IPS=RANGES, SAFARICOM_CALLBACK_PROXY_HOPS=0)
    def test_zero_hops_reads_the_socket_address(self):
        self.assertTrue(self._allowed('203.0.113.9', remote='196.201.214.17'))
