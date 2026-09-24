"""Boot-time deployment guards (fail-fast on unsafe production configuration).

These are pure, unit-testable predicates called from ``config/settings/production.py``
so a misconfiguration stops the process at import instead of silently degrading in
production. They mirror the existing ``STAGING_OTP_BYPASS`` guard.
"""
from django.core.exceptions import ImproperlyConfigured

# Kinds of user media that MUST survive a redeploy. KYC documents are also a
# regulatory retention obligation, not just a UX concern.
_DURABLE_MEDIA_REASON = (
    "User-uploaded media (KYC IDs/selfies, profile photos, attachments) is written "
    "to the local filesystem, which is ephemeral on Render/most PaaS — every upload "
    "is lost on redeploy (data loss + a KYC retention violation)."
)


def check_durable_media(*, debug: bool, use_s3: bool, allow_ephemeral: bool) -> None:
    """Refuse to boot a production process that would store media on ephemeral disk.

    Raises ``ImproperlyConfigured`` when ``DEBUG`` is off and durable object
    storage (``USE_S3``) is not enabled, unless the operator has *explicitly* opted
    into ephemeral media with ``ALLOW_EPHEMERAL_MEDIA=true`` (for deployments that
    genuinely accept no user media / KYC). A no-op in DEBUG (dev/CI use local disk).
    """
    if debug or use_s3 or allow_ephemeral:
        return
    raise ImproperlyConfigured(
        f"{_DURABLE_MEDIA_REASON} Set USE_S3=true and the AWS_*/R2 credentials to "
        "use durable object storage. If this deployment truly stores no user media, "
        "set ALLOW_EPHEMERAL_MEDIA=true to acknowledge the risk and boot anyway."
    )


def check_s3_credentials(*, use_s3: bool, bucket: str, access_key: str, secret_key: str) -> None:
    """When S3/R2 is enabled, require the credentials so it fails at boot with a
    clear message rather than on the first upload."""
    if not use_s3:
        return
    missing = [
        name for name, val in (
            ("AWS_STORAGE_BUCKET_NAME", bucket),
            ("AWS_ACCESS_KEY_ID", access_key),
            ("AWS_SECRET_ACCESS_KEY", secret_key),
        ) if not val
    ]
    if missing:
        raise ImproperlyConfigured(
            "USE_S3 is enabled but these required credentials are missing: "
            + ", ".join(missing)
        )


def check_callback_allowlist(*, mpesa_base_url: str, allowlist) -> None:
    """Refuse to boot against live Daraja with M-Pesa callbacks open to anyone.

    The callback endpoints credit members and settle payouts on what the body
    says. With ``SAFARICOM_CALLBACK_IPS`` empty, anyone who can reach them can
    post a fake "paid". That is tolerable against the sandbox, where no real
    money moves, and nowhere else. Every entry must also parse as an address or
    CIDR range, so a typo fails here rather than blocking Safaricom later.
    """
    import ipaddress
    from urllib.parse import urlparse

    for entry in allowlist:
        try:
            ipaddress.ip_network(entry.strip(), strict=False)
        except ValueError:
            raise ImproperlyConfigured(
                f"SAFARICOM_CALLBACK_IPS entry {entry!r} is not an IP address or CIDR range."
            )

    host = (urlparse(mpesa_base_url).hostname or '').lower()
    if host.startswith('sandbox.') or not host:
        return
    if not [e for e in allowlist if e.strip()]:
        raise ImproperlyConfigured(
            f"MPESA_BASE_URL points at live Daraja ({host}) but SAFARICOM_CALLBACK_IPS "
            "is empty, so anyone could post a fake payment callback. Set it to "
            "Safaricom's callback ranges before going live."
        )
