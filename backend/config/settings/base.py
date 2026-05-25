from pathlib import Path
from datetime import timedelta
from decouple import config, Csv

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')

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
    # Runs 3× daily; only fires orders whose next_run_at has elapsed
    'execute-due-standing-orders': {
        'task': 'apps.contributions.tasks.execute_due_standing_orders',
        'schedule': crontab(minute=0, hour='8,12,18'),  # 8am, 12pm, 6pm EAT
    },
    # Ledger vs. legacy-field drift check — runs at 3am EAT
    'reconcile-contribution-balances': {
        'task': 'apps.contributions.tasks.reconcile_balances',
        'schedule': crontab(minute=0, hour=3),
    },
    # Detects B2C payments stuck in PROCESSING for > 15 min
    'recover-stale-processing-transactions': {
        'task': 'apps.ledger.tasks.recover_stale_processing_transactions',
        'schedule': crontab(minute='*/30'),  # every 30 minutes
    },
    # Fire due reminders every 30 minutes
    'fire-due-reminders': {
        'task': 'apps.reminders.tasks.fire_due_reminders',
        'schedule': crontab(minute='*/30'),
    },
}

# ─── Africa's Talking (SMS / OTP) ─────────────────────────────────────────────
AT_API_KEY   = config('AT_API_KEY',   default='')
AT_USERNAME  = config('AT_USERNAME',  default='sandbox')
AT_SENDER_ID = config('AT_SENDER_ID', default='WEPL')
