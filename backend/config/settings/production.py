from .base import *  # noqa: F403
from decouple import config, Csv
from django.core.exceptions import ImproperlyConfigured

DEBUG = False

# Structured JSON logs by default in production (ADR-0020); override with LOG_FORMAT.
LOGGING['handlers']['console']['formatter'] = config('LOG_FORMAT', default='json')  # noqa: F405

# ─── Hard safety guard ──────────────────────────────────────────────────────────
# The staging OTP bypass accepts a fixed '000000' code for ANY phone number. It
# must never be active in production. Fail fast at boot rather than silently
# shipping a universal OTP. (STAGING_OTP_BYPASS is loaded in base.py.)
if STAGING_OTP_BYPASS:  # noqa: F405
    raise ImproperlyConfigured(
        "STAGING_OTP_BYPASS must not be enabled when DEBUG=False — remove it "
        "from the production environment."
    )

ALLOWED_HOSTS = config('ALLOWED_HOSTS', cast=Csv())

CORS_ALLOW_ALL_ORIGINS = False
CORS_ALLOWED_ORIGINS = config('CORS_ALLOWED_ORIGINS', cast=Csv(), default='')
CORS_ALLOW_CREDENTIALS = True

# ─── Database ───────────────────────────────────────────────────────────────
# Preferred: a single DATABASE_URL (e.g. a Neon connection string, which carries
# sslmode=require). Falls back to the discrete DB_* vars for any platform that
# still injects them. CONN_HEALTH_CHECKS matters on serverless Postgres: after
# an autosuspend the pooled connection is dead, and the health check transparently
# reconnects instead of failing the first request with a broken pipe.
_database_url = config('DATABASE_URL', default='')

if _database_url:
    import dj_database_url
    DATABASES = {
        'default': dj_database_url.parse(
            _database_url,
            conn_max_age=60,
            conn_health_checks=True,
        )
    }
    DATABASES['default'].setdefault('OPTIONS', {})['connect_timeout'] = 10
else:
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': config('DB_NAME'),
            'USER': config('DB_USER'),
            'PASSWORD': config('DB_PASSWORD'),
            'HOST': config('DB_HOST'),
            'PORT': config('DB_PORT', default='5432'),
            'CONN_MAX_AGE': 60,
            'CONN_HEALTH_CHECKS': True,
            'OPTIONS': {
                'connect_timeout': 10,
            },
        }
    }

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config('REDIS_URL')],
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config('REDIS_CACHE_URL', default=config('REDIS_URL')),
        # Bound the per-process client pool so web + worker + beat can't collectively
        # exhaust Redis's `maxclients`, and keep socket timeouts short so a slow or
        # saturated Redis fails fast instead of pinning request threads (which then
        # hold connections open and make the exhaustion worse). Pair with the
        # fail-open throttles (apps.core.throttling) so a cache blip degrades rather
        # than 500s the API.
        "OPTIONS": {
            "pool_class": "redis.BlockingConnectionPool",
            "max_connections": config('REDIS_CACHE_MAX_CONNECTIONS', default=32, cast=int),
            "timeout": 5,                  # wait up to 5s for a free pooled connection
            "socket_connect_timeout": 2,
            "socket_timeout": 2,
        },
    }
}

# ─── Security headers ──────────────────────────────────────────────────────────
# Render (and most PaaS) terminate TLS at a proxy and forward the request to the
# app over HTTP with X-Forwarded-Proto: https. Trust that header so Django knows
# the original request was secure — otherwise SECURE_SSL_REDIRECT below would 301
# every request (including the /health/ check) into a redirect loop.
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_BROWSER_XSS_FILTER = True
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = 'DENY'
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True

# ─── Media storage (S3 / Cloudflare R2) ─────────────────────────────────────────
# User-uploaded media — KYC IDs/selfies and profile photos — MUST persist across
# deploys. Render's dyno filesystem is ephemeral, so the default local MEDIA
# storage silently loses every uploaded file on each redeploy (a data-loss and
# regulatory risk for KYC documents).
#
# Enable durable object storage by setting USE_S3=true plus the credentials below.
# Cloudflare R2 is S3-compatible: point AWS_S3_ENDPOINT_URL at the R2 endpoint.
# When USE_S3 is false, Django's default (local FileSystemStorage) is used, so
# this is fully opt-in and dev/CI are unaffected.
USE_S3 = config('USE_S3', default=False, cast=bool)

# Fail fast if production would store KYC/media on the ephemeral dyno disk. An
# operator can explicitly accept the risk (deployments with no user media) with
# ALLOW_EPHEMERAL_MEDIA=true. Mirrors the STAGING_OTP_BYPASS guard above.
from apps.core.deploy_checks import check_durable_media, check_s3_credentials
check_durable_media(
    debug=DEBUG,
    use_s3=USE_S3,
    allow_ephemeral=config('ALLOW_EPHEMERAL_MEDIA', default=False, cast=bool),
)

# Static files are served by WhiteNoise (compressed + content-hashed for cache
# busting). collectstatic runs in the Render build, generating the manifest.
STORAGES = {
    "default": {
        "BACKEND": "django.core.files.storage.FileSystemStorage",
    },
    "staticfiles": {
        "BACKEND": "whitenoise.storage.CompressedManifestStaticFilesStorage",
    },
}

if USE_S3:
    INSTALLED_APPS = [*INSTALLED_APPS, 'storages']   # noqa: F405

    AWS_STORAGE_BUCKET_NAME = config('AWS_STORAGE_BUCKET_NAME', default='')
    AWS_S3_REGION_NAME      = config('AWS_S3_REGION_NAME', default='auto')
    AWS_S3_ENDPOINT_URL     = config('AWS_S3_ENDPOINT_URL', default='') or None
    AWS_ACCESS_KEY_ID       = config('AWS_ACCESS_KEY_ID', default='')
    AWS_SECRET_ACCESS_KEY   = config('AWS_SECRET_ACCESS_KEY', default='')
    # Clear boot-time error if creds are missing, instead of a 500 on first upload.
    check_s3_credentials(
        use_s3=USE_S3,
        bucket=AWS_STORAGE_BUCKET_NAME,
        access_key=AWS_ACCESS_KEY_ID,
        secret_key=AWS_SECRET_ACCESS_KEY,
    )
    # KYC documents are sensitive: keep objects private and serve via signed URLs.
    AWS_DEFAULT_ACL       = None
    AWS_QUERYSTRING_AUTH  = True
    AWS_S3_FILE_OVERWRITE = False

    # User media → private S3; static stays on WhiteNoise.
    STORAGES["default"] = {"BACKEND": "storages.backends.s3.S3Storage"}
