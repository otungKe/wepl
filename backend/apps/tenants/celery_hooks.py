"""Tenant-context hygiene for Celery workers (Phase 6, P6-04 follow-up).

REST closes the RLS tenant context with ``TenantRLSMiddleware``; background jobs
had no equivalent, so a tenant pinned by one task could leak onto the next task
that reused the same (pooled) DB connection. These ``task_prerun``/``task_postrun``
hooks clear the context at both boundaries, making the worker default to the
permissive *system* context.

Tasks that must operate on a single tenant's rows should scope themselves
explicitly with ``apps.tenants.rls.tenant_context(tenant_id)`` — the prerun clear
guarantees they start from a clean slate.
"""
import logging

from celery.signals import task_postrun, task_prerun

from .rls import clear_current_tenant

logger = logging.getLogger(__name__)


def _safe_clear(where: str) -> None:
    try:
        clear_current_tenant()
    except Exception:  # pragma: no cover - hygiene must never break task execution
        logger.exception("Failed to clear tenant RLS context at %s", where)
    try:
        from apps.core.observability import clear as clear_log_context
        clear_log_context()
    except Exception:  # pragma: no cover
        pass


def _on_prerun(**_kwargs):
    # Start every task from a clean (system) context — never inherit a leaked tenant.
    _safe_clear("task_prerun")


def _on_postrun(**_kwargs):
    # Don't leave a tenant pinned on a pooled connection for the next task.
    _safe_clear("task_postrun")


def connect() -> None:
    """Idempotently wire the hooks. Called from TenantsConfig.ready()."""
    task_prerun.connect(_on_prerun, dispatch_uid="tenants.clear_tenant_prerun")
    task_postrun.connect(_on_postrun, dispatch_uid="tenants.clear_tenant_postrun")
