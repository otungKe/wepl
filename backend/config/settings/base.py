from pathlib import Path
from datetime import timedelta
from decouple import config, Csv
from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = config('SECRET_KEY')

# Staging only — allows OTP "000000" to pass without a real SMS gateway.
# Set STAGING_OTP_BYPASS=true in env. Must never be true in production.
STAGING_OTP_BYPASS = config('STAGING_OTP_BYPASS', default=False, cast=bool)

# Two-tier access model (ADR-0022, Phase B). Master switch for enforcing Tier-1
# (KYC-approved) on the *new* gated surfaces — community create/join, contribution
# create, chat. Default OFF so existing (unverified-active) users are unaffected;
# flip to true in production after a KYC push. The pre-existing money-path checks
# (contribute / request_advance) always enforce regardless of this flag.
ACCESS_TIER_ENFORCEMENT = config('ACCESS_TIER_ENFORCEMENT', default=False, cast=bool)

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

    # Unfold must precede the admin app — it overrides admin templates.
    'unfold',
    'unfold.contrib.filters',
    'unfold.contrib.forms',
    'config.apps.WeplAdminConfig',  # custom admin site (overview dashboard)
    'django.contrib.auth',
    'django.contrib.contenttypes',
    'django.contrib.sessions',
    'django.contrib.messages',
    'django.contrib.staticfiles',

    'corsheaders',
    'rest_framework',
    'rest_framework_simplejwt',
    'rest_framework_simplejwt.token_blacklist',
    'drf_spectacular',

    'apps.core.apps.CoreConfig',
    'apps.tenants.apps.TenantsConfig',
    'apps.audit.apps.AuditConfig',
    'apps.files.apps.FilesConfig',
    'apps.search.apps.SearchConfig',

    'apps.users.apps.UsersConfig',
    'apps.communities.apps.CommunitiesConfig',
    'apps.conversations.apps.ConversationsConfig',
    'apps.contributions.apps.ContributionsConfig',
    'apps.payments.apps.PaymentsConfig',
    'apps.activity.apps.ActivityConfig',
    'apps.notifications.apps.NotificationsConfig',
    'apps.mpesa.apps.MpesaConfig',
    'apps.ledger.apps.LedgerConfig',
    'apps.controls.apps.ControlsConfig',
    'apps.reminders.apps.RemindersConfig',
    'apps.backoffice.apps.BackofficeConfig',
    'apps.verification.apps.VerificationConfig',
    'django_celery_beat',
]

MIDDLEWARE = [
    'corsheaders.middleware.CorsMiddleware',
    'django.middleware.security.SecurityMiddleware',
    # Serves collected static files (admin + unfold assets) under ASGI/Daphne
    # with DEBUG=False — without this the admin CSS never loads in production.
    'whitenoise.middleware.WhiteNoiseMiddleware',
    'apps.core.middleware.RequestIdMiddleware',
    'django.contrib.sessions.middleware.SessionMiddleware',
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',
    'django.contrib.auth.middleware.AuthenticationMiddleware',
    'django.contrib.messages.middleware.MessageMiddleware',
    'django.middleware.clickjacking.XFrameOptionsMiddleware',
    # Resets the per-request RLS tenant context (set in TenantJWTAuthentication).
    'apps.tenants.middleware.TenantRLSMiddleware',
]

ROOT_URLCONF = 'config.urls'
WSGI_APPLICATION = 'config.wsgi.application'
ASGI_APPLICATION = 'config.asgi.application'
AUTH_USER_MODEL = 'users.User'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [BASE_DIR / 'templates'],
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
        # Tenant-aware JWT: pins the RLS tenant context for member requests.
        'apps.tenants.auth.TenantJWTAuthentication',
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
        'stk_push': '5/minute',   # per-user cap on STK prompts (curbs prompt-spam)
    },
    # OpenAPI schema generation (P1 #6).
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    # Safe default for any (future) generic/list views. Existing APIView endpoints
    # paginate explicitly (apps/core/pagination.py) and are unaffected.
    'DEFAULT_PAGINATION_CLASS': 'rest_framework.pagination.PageNumberPagination',
    'PAGE_SIZE': 30,
}

# ─── OpenAPI schema (drf-spectacular, P1 #6) ──────────────────────────────────
SPECTACULAR_SETTINGS = {
    'TITLE': 'WEPL API',
    'DESCRIPTION': 'Community-finance "Financial OS" — ledger-first backend.',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    # Document the versioned space only; the legacy /api/ prefix is the same map
    # kept for old binaries, so excluding it avoids duplicate operations.
    'PREPROCESSING_HOOKS': ['config.schema.only_versioned_paths'],
}

# ─── Logging (ADR-0020) ───────────────────────────────────────────────────────
# Structured JSON in production (LOG_FORMAT=json), readable console in dev. Every
# line carries request_id / tenant_id / actor_id via the ContextFilter.
LOG_FORMAT = config('LOG_FORMAT', default='console')   # 'console' | 'json'

LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'filters': {
        'context': {'()': 'apps.core.observability.ContextFilter'},
    },
    'formatters': {
        'console': {
            'format': '[{asctime}] {levelname} {name}: {message}',
            'style': '{',
            'datefmt': '%H:%M:%S',
        },
        'json': {'()': 'apps.core.observability.JSONFormatter'},
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': LOG_FORMAT,
            'filters': ['context'],
        },
    },
    'root': {'handlers': ['console'], 'level': 'INFO'},
    'loggers': {
        'apps':                {'handlers': ['console'], 'level': 'DEBUG',   'propagate': False},
        'django':              {'handlers': ['console'], 'level': 'INFO',    'propagate': False},
        'django.db.backends':  {'handlers': ['console'], 'level': 'WARNING', 'propagate': False},
    },
}

LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'Africa/Nairobi'
USE_I18N = True
USE_TZ = True

# ─── Currency (Phase 5) ───────────────────────────────────────────────────────
# Default transaction currency and the presentation currency used to consolidate
# multi-currency reports. Kept in config (not hardcoded in logic) so deployments
# in other markets need no code change. The Money value object still defaults to
# KES; set these to drive app-level currency behaviour and consolidated reporting.
DEFAULT_CURRENCY      = config('DEFAULT_CURRENCY', default='KES')
PRESENTATION_CURRENCY = config('PRESENTATION_CURRENCY', default=DEFAULT_CURRENCY)

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
    # Payments reconciliation: intent ↔ FT ↔ ledger drift (ADR-0014) — hourly
    'reconcile-payments': {
        'task': 'apps.payments.tasks.reconcile_payments',
        'schedule': crontab(minute=15),
    },
    # Purge soft-deleted files past the retention window (ADR-0018) — daily 3am EAT
    'purge-expired-files': {
        'task': 'apps.files.tasks.purge_expired_files',
        'schedule': crontab(minute=0, hour=3),
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
# Bound the SMTP socket so a stalled connection fails fast instead of hanging
# the sender (the KYC email is sent from a Celery worker; without a timeout a
# blocked send ties the worker up indefinitely).
EMAIL_TIMEOUT       = config('EMAIL_TIMEOUT', default=15, cast=int)
# Brevo HTTP API key (port 443). When set, transactional email is delivered via
# Brevo's API instead of SMTP — required on hosts (e.g. Render free tier) that
# block outbound SMTP. Leave blank to use the EMAIL_BACKEND above (dev/CI).
BREVO_API_KEY       = config('BREVO_API_KEY', default='')


# ─────────────────────────────────────────────────────────────
# Django admin theme — django-unfold (WEPL brand: forest green / gold)
# ─────────────────────────────────────────────────────────────
UNFOLD = {
    "SITE_TITLE": "WEPL Admin",
    "SITE_HEADER": "WEPL Platform Admin",
    "SITE_SUBHEADER": "Financial OS — operations console",
    "SITE_SYMBOL": "account_balance",
    "SHOW_HISTORY": True,
    "SHOW_VIEW_ON_SITE": False,
    "COLORS": {
        # WEPL forest-green scale (#1A5C38 ≈ 600), R G B per Unfold/Tailwind.
        "primary": {
            "50":  "232 244 237",
            "100": "209 233 220",
            "200": "163 211 185",
            "300": "116 189 150",
            "400": "70 167 115",
            "500": "46 125 79",
            "600": "26 92 56",
            "700": "21 74 45",
            "800": "15 61 36",
            "900": "10 46 27",
            "950": "6 31 18",
        },
    },
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Overview"),
                "items": [
                    {"title": _("Dashboard"), "icon": "dashboard", "link": reverse_lazy("admin:index")},
                ],
            },
            {
                "title": _("Identity & KYC"),
                "items": [
                    {"title": _("KYC profiles"), "icon": "badge", "link": reverse_lazy("admin:users_kycprofile_changelist"), "badge": "config.admin_site.kyc_pending_badge"},
                    {"title": _("Users"), "icon": "person", "link": reverse_lazy("admin:users_user_changelist")},
                    {"title": _("Role groups"), "icon": "groups", "link": reverse_lazy("admin:auth_group_changelist")},
                ],
            },
            {
                "title": _("Communities"),
                "items": [
                    {"title": _("Communities"), "icon": "diversity_3", "link": reverse_lazy("admin:communities_community_changelist")},
                    {"title": _("Memberships"), "icon": "co_present", "link": reverse_lazy("admin:communities_communitymembership_changelist")},
                    {"title": _("Join requests"), "icon": "how_to_reg", "link": reverse_lazy("admin:communities_communityjoinrequest_changelist")},
                    {"title": _("Conversations"), "icon": "forum", "link": reverse_lazy("admin:conversations_conversation_changelist")},
                ],
            },
            {
                "title": _("Contributions & funds"),
                "items": [
                    {"title": _("Contributions"), "icon": "savings", "link": reverse_lazy("admin:contributions_contribution_changelist")},
                    {"title": _("Disbursements"), "icon": "request_quote", "link": reverse_lazy("admin:contributions_disbursementrequest_changelist")},
                    {"title": _("Welfare funds"), "icon": "volunteer_activism", "link": reverse_lazy("admin:contributions_welfarefund_changelist")},
                    {"title": _("Welfare claims"), "icon": "medical_services", "link": reverse_lazy("admin:contributions_welfareclaim_changelist")},
                    {"title": _("Emergency advances"), "icon": "emergency", "link": reverse_lazy("admin:contributions_emergencyadvance_changelist")},
                ],
            },
            {
                "title": _("Ledger (book of record)"),
                "items": [
                    {"title": _("Journal entries"), "icon": "menu_book", "link": reverse_lazy("admin:ledger_journalentry_changelist")},
                    {"title": _("Accounts"), "icon": "account_tree", "link": reverse_lazy("admin:ledger_account_changelist")},
                    {"title": _("Account balances"), "icon": "balance", "link": reverse_lazy("admin:ledger_accountbalance_changelist")},
                    {"title": _("Financial transactions"), "icon": "receipt_long", "link": reverse_lazy("admin:ledger_financialtransaction_changelist")},
                ],
            },
            {
                "title": _("Payments (M-Pesa)"),
                "items": [
                    {"title": _("STK requests"), "icon": "smartphone", "link": reverse_lazy("admin:mpesa_mpesastkrequest_changelist")},
                    {"title": _("C2B transactions"), "icon": "payments", "link": reverse_lazy("admin:mpesa_mpesac2btransaction_changelist")},
                ],
            },
            {
                "title": _("System"),
                "items": [
                    {"title": _("Notifications"), "icon": "notifications", "link": reverse_lazy("admin:notifications_notification_changelist")},
                    {"title": _("Reminders"), "icon": "alarm", "link": reverse_lazy("admin:reminders_reminder_changelist")},
                    {"title": _("Outbox events"), "icon": "outbox", "link": reverse_lazy("admin:core_outboxevent_changelist")},
                ],
            },
        ],
    },
}
