# ADR-0017: Search architecture

- **Status:** Accepted (permission-filtered Postgres-FTS search built; stored indexes & external engine deferred)
- **Date:** 2026-06-24
- **Relates to:** Platform Hardening Review §3.1 (Platform Gaps) + Action Plan P2 #13.

## Context

Search was ad-hoc `icontains` filtering inside `communities.discover` and user
lookup: a table scan at scale that **ignores permissions and ranking**. There was
no search service, and crucially nothing stopped a query from returning rows the
actor can't see.

## Decision

A dedicated **`search` app** exposing one service and endpoint, with two
non-negotiable properties: **permission-filtered at query time** and **ranked**.

- **`SearchService.search(actor, q, types, limit)`** searches communities,
  contributions and users, returning ranked, lightweight results grouped by type.
- **Permission filtering is in the base queryset** (never a post-filter), so a
  private community, a closed contribution, or a non-discoverable user can never
  appear:
  - communities: public **or** the actor is an active member;
  - contributions: `open` **or** the actor is a participant / a member of the
    owning community;
  - users: only `privacy_prefs.discoverable` (default when no row), matched by name
    or exact phone.
  Tenant scope is applied to communities/contributions when the request is pinned.
- **Ranking** uses Postgres full-text search (`SearchVector` weighted by field +
  `SearchRank`) for the long-text entities; users match on name/phone. No DB
  extension required.
- **Endpoint:** `GET /api/search/?q=&type=&limit=` (also under `/api/v1/`).

## Consequences

- **+** One permission-safe, ranked search seam for the product, replacing scattered
  `icontains`. The IDOR-by-search class is closed by construction (base-queryset
  filtering).
- **+** No schema change — read-only over existing data; ships immediately.
- **−** Query-time `SearchVector` (no stored `tsvector`/GIN index) is fine to tens of
  thousands of rows but not millions — see v2.
- **−** Messages aren't searched yet (higher volume + per-conversation membership join).

## Deferred (documented)

- **Stored `SearchVectorField` + GIN indexes** (maintained via triggers/signals) for
  performance — the v1→v1.5 step before an external engine.
- **OpenSearch/Meilisearch backend** behind the same `SearchService` seam (v2), for
  typo-tolerance, facets and cross-entity ranking at scale.
- **Message search** (membership-scoped) and **global mixed-type ranking**.
- Migrate `communities.discover` / user lookup onto `SearchService`.

## Alternatives considered

- **Stored tsvector + GIN now.** Rejected for v1: it needs migrations + trigger
  maintenance on several models; query-time FTS establishes the permission-safe seam
  with zero schema risk, and the index is a drop-in follow-up.
- **Trigram (`pg_trgm`) similarity.** Deferred — needs the extension; FTS covers the
  ranked v1 without it.
