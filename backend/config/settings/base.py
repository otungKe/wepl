from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')

# Staging only — allows OTP "000000" to pass without a real SMS gateway.
# Set STAGING_OTP_BYPASS=true in env. Must never be true in production.
STAGING_OTP_BYPASS = config('STAGING_OTP_BYPASS', default=False, cast=bool)

# ─── Firebase (FCM push notifications) ───────────────────────────────────────
# Path to a Firebase service-account JSON file (download from Firebase Console
# → Project Settings → Service Accounts → Generate new private key).
# Leave blank to disable push notifications — the app will still work without it.
FIREBASE_CREDENTIALS_JSON = config('FIREBASE_CREDENTIALS_JSON', default='')

# ─── Sentry (error tracking) ──────────────────────────────────────────────────
# Set SENTRY_DSN in your environment to enable. Leave blank to disable.
SENTRY_DSN = config('SENTRY_DSN', default='')
if SENTRY_DSN:
    import sentry_sdk
    from sentry_sdk.integrations.django import DjangoIntegration
    from sentry_sdk.integrations.celery import CeleryIntegration

    sentry_sdk.init(
        dsn=SENTRY_DSN,
        integrations=[DjangoIntegration(), CeleryIntegration()],
        traces_sample_rate=0.2,   # 20% of requests traced for performance
        send_default_pii=False,   # do not send personally identifiable info
    )

INSTALLED_APPS = [
    'daphne',
    'channels',

    'django.contrib.admin',
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',

    'apps.core.apps.CoreConfig',

    'apps.users.apps.UsersConfig',
    'apps.communities.apps.CommunitiesConfig',
    'apps.conversations.apps.ConversationsConfig',
    'apps.contributions.apps.ContributionsConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.activity.apps.ActivityConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.mpesa.apps.MpesaConfig',
    'apps.ledger.apps.LedgerConfig',
    'apps.reminders.apps.RemindersConfig',
    'django_celery_beat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    'apps.core.middleware.RequestIdMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
AUTH_USER_MODEL = 'users.User'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

AUTH_PASSWORD_VALIDATORS = [
    {'NAME': 'django.contrib.auth.password_validation.UserAttributeSimilarityValidator'},
    {'NAME': 'django.contrib.auth.password_validation.MinimumLengthValidator'},
    {'NAME': 'django.contrib.auth.password_validation.CommonPasswordValidator'},
    {'NAME': 'django.contrib.auth.password_validation.NumericPasswordValidator'},
]

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=60),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=7),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "BLACKLIST_AFTER_ROTATION": True,
    "ROTATE_REFRESH_TOKENS": True,
}

REST_FRAMEWORK = {
    'DEFAULT_AUTHENTICATION_CLASSES': (
        'rest_framework_simplejwt.authentication.JWTAuthentication',
    ),
    'EXCEPTION_HANDLER': 'apps.core.exceptions.custom_exception_handler',
    'DEFAULT_THROTTLE_CLASSES': [
        'rest_framework.throttling.AnonRateThrottle',
        'rest_framework.throttling.UserRateThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {
        'anon': '60/minute',
        'user': '300/minute',
        'otp_request': '3/hour',
        'pin_login': '5/minute',
    },
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

MEDIA_URL = '/media/'
MEDIA_ROOT = BASE_DIR / 'media'

DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# ─── M-Pesa ───────────────────────────────────────────────────────────────────
MPESA_CONSUMER_KEY       = config('MPESA_CONSUMER_KEY',       default='')
MPESA_CONSUMER_SECRET    = config('MPESA_CONSUMER_SECRET',    default='')
MPESA_SHORTCODE          = config('MPESA_SHORTCODE',          default='174379')
MPESA_PASSKEY            = config('MPESA_PASSKEY',            default='')
MPESA_CALLBACK_URL       = config('MPESA_CALLBACK_URL',       default='')
MPESA_BASE_URL           = config('MPESA_BASE_URL',           default='https://sandbox.safaricom.co.ke')
MPESA_B2C_INITIATOR_NAME      = config('MPESA_B2C_INITIATOR_NAME',      default='testapi')
MPESA_B2C_SECURITY_CREDENTIAL = config('MPESA_B2C_SECURITY_CREDENTIAL', default='')
MPESA_B2C_RESULT_URL          = config('MPESA_B2C_RESULT_URL',          default='')
MPESA_B2C_TIMEOUT_URL         = config('MPESA_B2C_TIMEOUT_URL',         default='')

# Safaricom callback IP allowlist.  Empty = all IPs allowed (dev/sandbox).
# In production: populate from Daraja portal or Safaricom account team.
# Example: ['196.201.214.200', '196.201.216.200']
SAFARICOM_CALLBACK_IPS: list = []

# ─── Celery ───────────────────────────────────────────────────────────────────
CELERY_BROKER_URL         = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_RESULT_BACKEND     = config('REDIS_URL', default='redis://127.0.0.1:6379/0')
CELERY_ACCEPT_CONTENT     = ['json']
CELERY_TASK_SERIALIZER    = 'json'
CELERY_RESULT_SERIALIZER  = 'json'
CELERY_TIMEZONE           = 'Africa/Nairobi'
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_ACKS_LATE     = True       # re-queue on worker crash
CELERY_WORKER_PREFETCH_MULTIPLIER = 1  # fair dispatch

CELERY_TASK_QUEUES_DEFAULT = 'default'
CELERY_TASK_DEFAULT_QUEUE  = 'default'
CELERY_TASK_ROUTES = {
    'apps.core.tasks.*':           {'queue': 'notifications'},
    'apps.notifications.tasks.*':  {'queue': 'notifications'},
    'apps.payments.tasks.*':       {'queue': 'payments'},
    'apps.mpesa.tasks.*':          {'queue': 'payments'},
    'apps.ledger.tasks.*':         {'queue': 'financial'},
    'apps.contributions.tasks.*':  {'queue': 'financial'},
}

# django-celery-beat: store schedule in the database
INSTALLED_APPS_BEAT = ['django_celery_beat']

# Scheduled tasks (run via Celery Beat)
from celery.schedules import crontab
CELERY_BEAT_SCHEDULE = {
    # Transactional outbox relay — deliver durably-stored domain events (Phase 2).
    # Seconds-interval (crontab is minute-granularity) for timely notifications.
    'process-outbox': {
        'task': 'apps.core.tasks.process_outbox',
        'schedule': 10.0,  # every 10 seconds
    },
    # Runs 3× daily; only fires orders whose next_run_at has elapsed
    'execute-due-standing-orders': {
        'task': 'apps.contributions.tasks.execute_due_standing_orders',
        'schedule': crontab(minute=0, hour='8,12,18'),  # 8am, 12pm, 6pm EAT
    },
    # Detects B2C payments stuck in PROCESSING for > 15 min
    'recover-stale-processing-transactions': {
        'task': 'apps.ledger.tasks.recover_stale_processing_transactions',
        'schedule': crontab(minute='*/30'),  # every 30 minutes
    },
    # Ledger integrity: trial balance == 0 and projection == replay — runs 2am EAT
    'reconcile-ledger': {
        'task': 'apps.ledger.tasks.reconcile_ledger',
        'schedule': crontab(minute=0, hour=2),
    },
    # Fire due reminders every 30 minutes
    'fire-due-reminders': {
        'task': 'apps.reminders.tasks.fire_due_reminders',
        'schedule': crontab(minute='*/30'),
    },
    # Notify borrowers with overdue emergency advances — runs daily at 9am EAT
    'notify-overdue-advances': {
        'task': 'apps.contributions.tasks.notify_overdue_advances',
        'schedule': crontab(minute=0, hour=9),
    },
}

# ─── Payment rail selection (apps.payments.providers.registry) ────────────────
#   'mpesa' → Daraja; 'fake' → no-network stub; '' → auto (fake under DEBUG)
PAYMENT_PROVIDER = config('PAYMENT_PROVIDER', default='')

# ─── SMS / OTP delivery ───────────────────────────────────────────────────────
# Gateway selection consumed by apps.users.sms.get_sms_gateway():
#   'at'      → Africa's Talking (real SMS)
#   'console' → log the message only (dev / staging / CI)
#   ''        → auto: 'console' under DEBUG, 'at' otherwise
SMS_BACKEND = config('SMS_BACKEND', default='')

# ─── Africa's Talking (SMS / OTP) ─────────────────────────────────────────────
AT_API_KEY   = config('AT_API_KEY',   default='')
AT_USERNAME  = config('AT_USERNAME',  default='sandbox')
AT_SENDER_ID = config('AT_SENDER_ID', default='WEPL')

# ─── Email delivery (KYC verification links, etc.) ────────────────────────────
# Defaults to the console backend, which writes the full message — including the
# KYC verification link — to the logs, mirroring SMS_BACKEND=console for OTP.
# Without this, production fell back to Django's SMTP default (localhost:25) and
# silently failed: nothing sent, nothing logged. For real delivery, set
# EMAIL_BACKEND to an SMTP backend and provide the EMAIL_HOST_* credentials.
EMAIL_BACKEND = config(
    'EMAIL_BACKEND',
    default='django.core.mail.backends.console.EmailBackend',
)
DEFAULT_FROM_EMAIL  = config('DEFAULT_FROM_EMAIL', default='WEPL <no-reply@wepl.app>')
EMAIL_HOST          = config('EMAIL_HOST', default='')
EMAIL_PORT          = config('EMAIL_PORT', default=587, cast=int)
EMAIL_HOST_USER     = config('EMAIL_HOST_USER', default='')
EMAIL_HOST_PASSWORD = config('EMAIL_HOST_PASSWORD', default='')
EMAIL_USE_TLS       = config('EMAIL_USE_TLS', default=True, cast=bool)
