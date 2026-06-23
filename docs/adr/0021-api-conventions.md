# ADR-0021: API conventions — versioning, OpenAPI schema, pagination default

- **Status:** Accepted (implemented in `config/`)
- **Date:** 2026-06-23
- **Relates to:** Platform Hardening Review §1.2 + Action Plan P1 #6.

## Context

`REST_FRAMEWORK` had an exception handler + throttles but **no API versioning, no
OpenAPI schema, and no default pagination**. The review's verdict: the HTTP API is
"pre-public-grade" — a typed client can't be generated, and a breaking change can't
be made safely because old mobile binaries live for years. The constraint: existing
mobile clients call `/api/<app>/…` today and must keep working.

## Decision

Establish the conventions **without breaking the live API**.

- **Versioning by URL, non-breaking.** The whole API map is factored into
  `config/api_urls.py` and mounted **twice**: at the legacy `/api/` prefix (what
  shipped binaries call) and at `/api/v1/` (what new clients target). One list, so
  the two mounts can't drift; a future breaking change ships as `/api/v2/` while
  `/api/v1/` stays stable. No DRF versioning *class* is forced (it would require
  per-request URL `version` capture and complicate routing); the URL space itself is
  the seam, which is what matters for evolvability.
- **OpenAPI schema via drf-spectacular.** `/api/schema/` (spec) + `/api/schema/
  swagger-ui/` + `/api/schema/redoc/`. A preprocessing hook documents the `/api/v1/`
  paths only (the legacy mount is the same operations, so it's excluded to avoid
  duplicates). An `OpenApiAuthenticationExtension` teaches the schema that our
  (subclassed) JWT auth is HTTP bearer JWT.
- **Default pagination class.** `PageNumberPagination` (PAGE_SIZE 30) is set as the
  DRF default. The existing endpoints are hand-rolled `APIView`s that paginate
  explicitly (`apps/core/pagination.py`'s cursor paginator for financial feeds), so
  this default only governs future generic/list views — a safe, correct baseline.

## Consequences

- **+** A generated, browsable schema → typed web/mobile clients and drift detection
  (the review noted hand-maintained clients have already drifted).
- **+** A stable versioned URL space to evolve against; nothing existing breaks.
- **−** Because most endpoints are hand-rolled `APIView`s without serializers,
  spectacular emits "unable to guess serializer" fallbacks — the schema generates and
  is valid, but request/response bodies for those operations are generic until views
  are annotated with `@extend_schema` (incremental follow-up).

## Deferred (would be breaking — need client coordination)

- **Standard error envelope** `{error: {code, message, details}}`. The handler today
  returns `{"error": "…"}` / `{"errors": […]}`, which mobile parses; changing the shape
  is a breaking change and belongs behind the `/api/v2/` boundary (or a negotiated
  rollout). Documented, not done.
- **Cursor pagination as the global default / migrating list endpoints** (notifications,
  conversations) onto it — changes response shapes, so likewise deferred to a versioned
  cutover.
- **`@extend_schema` annotations** per endpoint, and **django-filter** backends.

## Alternatives considered

- **`URLPathVersioning` with a single `/api/v<n>/` route + `version` kwarg.** Rejected
  for now: it would break every existing `/api/…` caller. The dual-mount keeps both.
- **`AcceptHeaderVersioning`.** Non-breaking but invisible in URLs and harder to debug;
  URL versioning is more discoverable for a mobile API.
