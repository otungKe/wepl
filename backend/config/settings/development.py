from .base import *  # noqa: F403
from decouple import config

DEBUG = True

ALLOWED_HOSTS = ['*']

CORS_ALLOW_ALL_ORIGINS = True
CORS_ALLOW_CREDENTIALS = True

# PostgreSQL (use docker-compose postgres or a local install — never SQLite)
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': config('DB_NAME', default='wepl'),
        'USER': config('DB_USER', default='wepl'),
        'PASSWORD': config('DB_PASSWORD', default='password'),
        'HOST': config('DB_HOST', default='localhost'),
        'PORT': config('DB_PORT', default='5432'),
    }
}

CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config('REDIS_URL', default='redis://127.0.0.1:6379/0')],
        },
    },
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config('REDIS_URL', default='redis://127.0.0.1:6379/1'),
    }
}

# Show emails/OTPs in console during development
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# ─── MinIO (local S3-compatible storage for development) ──────────────────────
# Run MinIO with:
#   docker run -p 9000:9000 -p 9001:9001 \
#     -e MINIO_ROOT_USER=wepl -e MINIO_ROOT_PASSWORD=password123 \
#     minio/minio server /data --console-address ":9001"
# Then open http://localhost:9001 and create a bucket called "wepl-media".
#
# Set USE_MINIO=True in your .env to activate (defaults to local filesystem).
_USE_MINIO = config('USE_MINIO', default=False, cast=bool)

if _USE_MINIO:
    INSTALLED_APPS = [*INSTALLED_APPS, 'storages']   # noqa: F405

    # django-storages S3 backend pointed at local MinIO
    DEFAULT_FILE_STORAGE  = 'storages.backends.s3boto3.S3Boto3Storage'
    STATICFILES_STORAGE   = 'storages.backends.s3boto3.S3StaticStorage'

    AWS_ACCESS_KEY_ID       = config('MINIO_ACCESS_KEY', default='wepl')
    AWS_SECRET_ACCESS_KEY   = config('MINIO_SECRET_KEY', default='password123')
    AWS_STORAGE_BUCKET_NAME = config('MINIO_BUCKET',     default='wepl-media')
    AWS_S3_ENDPOINT_URL     = config('MINIO_ENDPOINT',   default='http://localhost:9000')
    AWS_S3_REGION_NAME      = 'us-east-1'   # MinIO ignores this but boto3 requires it
    AWS_DEFAULT_ACL         = None           # Bucket policy controls access
    AWS_S3_FILE_OVERWRITE   = False          # Keep original filenames
    AWS_QUERYSTRING_AUTH    = False          # Plain URLs (dev only — bucket is public read)
    # Production: set AWS_QUERYSTRING_AUTH = True and bucket to private
    AWS_S3_OBJECT_PARAMETERS = {'CacheControl': 'max-age=86400'}

    MEDIA_URL = f"{AWS_S3_ENDPOINT_URL}/{AWS_STORAGE_BUCKET_NAME}/"

# ─── Relaxed rate limits for development/testing ──────────────────────────────
# Production limits are defined in base.py. These overrides prevent the
# throttle from blocking repeated test registrations during development.
REST_FRAMEWORK = {
    **REST_FRAMEWORK,                           # noqa: F405  inherit base config
    'DEFAULT_THROTTLE_RATES': {
        'anon':        '600/minute',
        'user':        '600/minute',
        'otp_request': '60/hour',    # was 3/hour  — allows repeated test signups
        'pin_login':   '60/minute',  # was 5/minute — allows repeated test logins
        'stk_push':    '5/minute',   # per-user cap on STK prompts (curbs prompt-spam)
        'invite_lookup': '600/hour',  # relaxed for tests; prod uses base.py rates
        'join_request':  '600/hour',
    },
}

# ─── Logging ──────────────────────────────────────────────────────────────────
# Inherited from base.py (readable console format + request/tenant/actor context).
# Set LOG_FORMAT=json to preview structured logs locally.
