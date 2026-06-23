"""Shared API URL map (P1 #6 — API versioning).

Mounted twice by ``config/urls.py``: at ``/api/`` (the original, unversioned paths
that existing mobile binaries call) and at ``/api/v1/`` (the versioned space new
clients should target). Keeping one list means the two mounts never drift, and a
future breaking change ships as ``/api/v2/`` while ``/api/v1/`` stays stable.
"""
from django.urls import include, path

urlpatterns = [
    path('users/',         include('apps.users.urls')),
    path('communities/',   include('apps.communities.urls')),
    path('conversations/', include('apps.conversations.urls')),
    path('contributions/', include('apps.contributions.urls')),
    path('payments/',      include('apps.payments.urls')),
    path('activity/',      include('apps.activity.urls')),
    path('notifications/', include('apps.notifications.urls')),
    path('mpesa/',         include('apps.mpesa.urls')),
    path('reminders/',     include('apps.reminders.urls')),
    path('ledger/',        include('apps.ledger.urls')),
]
