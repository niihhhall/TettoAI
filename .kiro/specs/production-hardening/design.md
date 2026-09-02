# Design — Production Hardening

Status: DRAFT (locks after Open decisions D1–D5 are confirmed)
Baseline: `docs/kiro-production-prd-v2.md`. Reflects recommended defaults.

## Architecture deltas (from skeleton → production)

### 1. Durable async + worker topology (D3)
Replace fire-and-forget `BackgroundTasks` for the heavy path with a durable job:
- Persist an `inbound_events` row keyed by Twilio `MessageSid` on receipt (idempotency).
- Enqueue processing to a durable queue (Redis + RQ/arq, or a Postgres-backed
  outbox polled by a worker). MVP: single web worker + Redis; scale later.
- Move onboarding buffer and WebSocket fan-out to Redis (pub/sub) so N workers agree.
- Add session states `PROCESSING` and `FAILED`; a crash/redeploy resumes or surfaces failure.

### 2. Auth & tenancy (D4, R2/R3)
- New `operators` table (id, company_id, email, password_hash, role, created_at).
- Login endpoint issues a short-lived JWT (company_id claim). FastAPI dependency
  `require_operator()` resolves company and injects it into every inspection/crew query.
- Repository read methods gain a `company_id` filter; WebSocket authenticates on connect
  and only receives its tenant's events.

### 3. CRM dispatch (D1, R10)
- `_submit()` no longer auto-pushes. Approval endpoint:
  resolve company → `crm_webhook_url` → POST `{...package, pdf_url}` →
  `raise_for_status()` → persist `crm_status` + `crm_response_at` → broadcast an
  `inspection.updated` event. Retry with backoff; record FAILED for operator retry.

### 4. Bounty state machine (R8, R9)
- `lock_bounty` becomes conditional: credit only on approval, `WHERE bounty_status='APPROVED'`
  transition to `PAID` in one transaction, guarded so a retry cannot double-credit.
- Submission sets `APPROVED`-eligible only after PDF success; PDF failure → `FAILED`, no credit.

### 5. Location & evidence (R4, R5, R7)
- Parse Twilio `Latitude`/`Longitude` (and address fields) in `parse_inbound`.
- State 2 calls `services.reverse_geocode` → persist address/city/county → fetch
  municipal code → store on jobsite. Remove hard-coded Dallas values from PDF payload.
- State 3 validates content types and min/max photo count; pass `photos` to the PDF payload.
- State 5 (explicit) blocks submit until prerequisites met.

### 6. Contract & realtime (R11, R12)
- Inspection card gains `created_at`, `voice_note_url`, `supplement_value`.
- Frontend `Inspection` type + drawer add timestamp, audio player, and supplement value;
  remove the fabricated local `PAID`. Approval reflects the backend `crm_status`.

### 7. Security hardening (N2–N4)
- Twilio signature verification middleware on the webhook.
- Media fetch SSRF guard: allow only Twilio media hosts; strip auth on redirect (already done).
- Private R2; serve via short-lived signed URLs from an authenticated backend route.
- Exact `CORS_ORIGINS`; security headers; startup credential validation per service.

### 8. Frontend consolidation (Phase 3)
- Route only the FastAPI inspection plane in production; remove/guard Supabase pages.
- Fix package name / titles / branding; add login UI; add loading/error/empty states;
  dialog roles + focus trap + keyboard-activable rows.

### 9. Data model additions (migrations, forward-only)
- `operators`, `inbound_events` (MessageSid unique), jobsite geo/code columns already exist,
  `inspection_sessions`: add `crm_status`, `crm_response_at`, `supplement_value`, and a
  partial unique index for one active session per crew.

## Testing strategy
- Unit: state transitions, bounty idempotency, CRM success/failure, geocode parsing.
- Integration: PgRepository against a real/branch Postgres; Modal contract; Twilio
  signature; CRM push (mock server asserting payload + pdf_url); duplicate MessageSid.
- Frontend: WebSocket reconnect/dedupe, approval reflects server state, auth guard.

## Rollout
Phase 1 (security) → Phase 2 (correctness) → Phase 3 (frontend) → Phase 4 (ops), each
shippable and reversible. Each phase gates on its tests + build passing in CI.
