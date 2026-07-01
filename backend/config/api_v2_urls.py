"""Versioned (/api/v2/) endpoints that intentionally diverge from the v1 contract.

ADR-0021: `/api/` and `/api/v1/` share one map (``config.api_urls``) and hold the
stable contract shipped mobile binaries depend on. A **breaking** change ships
under `/api/v2/` instead of mutating that shape. Only endpoints that have such a
change live here; everything else stays on the shared v1 map.

Currently: the activity feed's keyset **cursor pagination** (response
``{next, previous, results}``, ADR-0016) — its shape differs from the legacy
``{count, results, has_more}`` feed, so it lives here rather than breaking
existing callers of `/api/activity/`.
"""
from django.urls import path

from apps.activity.views import ActivityFeedViewV2

urlpatterns = [
    path('activity/', ActivityFeedViewV2.as_view()),
]
