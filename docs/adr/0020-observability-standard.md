# ADR-0020: Observability standard — structured logging & health probes

- **Status:** Accepted (logging + health implemented; metrics/tracing seam documented)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §1.4 + Action Plan P1 #8.

## Context

Observability stopped at Sentry: no structured logs, no request correlation, no
liveness/readiness split, no metrics. The first real incident would be debugged
blind — you couldn't grep one request across services or tell an orchestrator the
difference between "process dead" and "dependency down."

## Decision

### Structured logging with request context
- **`apps/core/observability.py`**: a thread-local log context + a `ContextFilter`
  that stamps `request_id`, `tenant_id`, `actor_id` onto every record, and a
  `JSONFormatter` that emits one JSON object per line (ts, level, logger, message,
  module, the context fields, and any exception).
- **Binding points** (no work at call sites): `request_id` in
  `RequestIdMiddleware`; `actor_id` in the JWT auth class once the user resolves;
  `tenant_id` in the tenant-aware auth class when it pins the tenant. The context is
  **cleared at request end (middleware `finally`) and at Celery task boundaries**, so
  nothing leaks across requests/tasks on a reused thread.
- **Config** moved to `base.py` and parameterised by `LOG_FORMAT`: readable
  `console` in dev, `json` in production. One canonical `LOGGING` dict for all
  environments.

### Health probes
- **`/health/live/`** — liveness: process is up; **no** dependency checks (a flaky
  dependency must not trigger a restart loop).
- **`/health/ready/`** — readiness: checks DB + cache; a failure takes the instance
  out of rotation (503) without restarting it.
- **`/health/`** retained as an alias of readiness for the existing uptime monitor.

## Consequences

- **+** Every log line is greppable by request/tenant/actor — real incident tracing,
  and it dovetails with the audit log (ADR-0019) and request-id header.
- **+** Correct k8s/Render probe semantics (liveness vs readiness).
- **−** JSON logs are less human-readable; mitigated by `LOG_FORMAT=console` in dev.

## Deferred (seam, not built) — metrics & tracing

Metrics and tracing are **infrastructure-coupled** (a scrape target / collector,
dashboards, alert rules) and add little without that ops work, so they are scoped
out of this PR and recorded as the next steps:

- **Metrics:** `django-prometheus` for request RED metrics, Celery queue depth/task
  latency, outbox lag, WS connections, payment success rate — exposed at `/metrics`.
  Prefer the middleware-only integration first (request metrics) before the DB/cache
  engine wrappers, to avoid touching `DATABASES`.
- **Tracing:** OpenTelemetry around HTTP → service → DB → Celery.

The logging context (request_id/tenant_id/actor_id) is the correlation key both will
reuse.

## Alternatives considered

- **`python-json-logger` / `structlog`.** Fine libraries, but the formatter here is
  ~20 lines with zero new deps and full control of the envelope; revisit structlog if
  we want bound-logger ergonomics.
- **One `/health/` for everything.** Rejected — conflating liveness and readiness
  causes restart loops when only a dependency is down.
