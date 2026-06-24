# ADR-0018: File storage & media pipeline

- **Status:** Accepted (pipeline + signed access + scan seam + retention built; consumer migration deferred)
- **Date:** 2026-06-24
- **Relates to:** Platform Hardening Review §3.2 (Platform Gaps) + Action Plan P2 #13.

## Context

User media (avatars, KYC docs, chat attachments, payment evidence) went straight
to `ImageField`/`FileField` with **no validation pipeline, no size/type limits, no
virus-scan seam, no signed-URL access, and no retention/deletion policy**. That is a
real security gap (unbounded uploads, spoofable/served-blindly content) and a
capability the review lists as unbuilt.

## Decision

A dedicated **`files` app** as the single door for persisting user media.

- **`StoredFile`** — one row per object: owner, `kind`, declared `content_type`,
  `size_bytes`, `checksum_sha256`, `scan_status`, tenant, soft-delete marker. Bytes
  live in the configured storage backend (local FS in dev, S3/R2 in prod) via
  Django's storage abstraction — no backend coupling in app code.
- **`FileService.save`** — the validation pipeline: per-`kind` allow-lists for
  content type **and** max size (e.g. avatars ≤5 MB images; KYC/evidence ≤10 MB
  images+PDF; chat ≤25 MB media), content checksum, then store + enqueue the scan.
- **Virus-scan seam** — `tasks.scan_file` marks `SKIPPED` when no scanner is
  configured (non-regressive vs. today's no-scan), and is where a real engine
  (ClamAV / scanning API) + magic-byte content sniffing plug in to set
  `CLEAN`/`INFECTED`. Downloads are blocked only for `INFECTED`.
- **Signed, time-limited access** — a download URL carries a `TimestampSigner` token
  bound to the file id (the capability), so `<img src>` works without a session
  while access is unguessable and expires; tampered/expired tokens and
  infected/soft-deleted files are refused.
- **Retention** — `tasks.purge_expired_files` (daily beat) hard-deletes soft-deleted
  files (storage object + row) past the retention window.

## Consequences

- **+** A validated, size/type-bounded, scannable, signed-access, retention-managed
  pipeline — closes the unbounded-upload / blind-serve gap and gives new features a
  ready home.
- **+** Storage-backend-agnostic; S3/R2 in prod needs only settings.
- **−** Content-type validation trusts the declared type for now; deep magic-byte
  verification is part of the scan seam (not yet implemented).
- **−** Existing avatar/KYC/attachment fields are **not yet migrated** onto `files`
  (below).

## Deferred (documented)

- **Migrate existing consumers** (`users.profile_photo`, KYC images, community photo,
  message attachment) onto `StoredFile` — additive now, then switch reads/writes,
  then drop the raw fields (a multi-step, client-coordinated change).
- **Real AV engine** + magic-byte sniffing in the scan hook.
- **CDN** in front of the signed-download endpoint, and **image variants/resizing**.

## Alternatives considered

- **Per-model `FileField` validators.** Rejected — scatters the rules, gives no
  central scan/retention/signed-access seam, and can't be reused across kinds.
- **Direct-to-S3 presigned uploads.** A good future optimisation (offload bytes from
  the app), but it still needs this record/validation/scan model; the server-side
  upload path ships first and the presign flow can layer on.
