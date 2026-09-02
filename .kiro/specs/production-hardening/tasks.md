# Tasks — Production Hardening

Baseline: `docs/kiro-production-prd-v2.md`. Requirement IDs (R#/N#) refer to `requirements.md`.
Check off tasks as completed. Each is scoped to be independently reviewable.

## Phase 0 — Foundation (no product decisions required)
- [x] 0.1 Add root `.gitignore` protecting secrets and generated dirs.
- [x] 0.2 Add Kiro steering (product/tech/structure).
- [x] 0.3 Add this spec (requirements/design/tasks).
- [ ] 0.4 Decide + execute git consolidation: init root repo; resolve nested `frontend/.git`
      (keep history vs. absorb). REQUIRES approval — do not force anything.
- [ ] 0.5 Consolidate PRDs to one canonical doc; fix version drift; delete/redirect the
      non-authoritative root v4; remove the dead `kiro-master-prd-v2.md` reference.
- [ ] 0.6 Add `backend/requirements-dev.txt` (pytest, ruff/mypy); add a task runner (Makefile
      or `noxfile`) and pin the frontend Node version (`engines`/`.nvmrc`).
- [ ] 0.7 Add CI (build + lint + tests for backend and frontend) — see 4.x, wired early.

## Phase 1 — Security launch blockers (R2, R3, N2–N4)
- [x] 1.1 `operators` table + migration; password hashing; login endpoint issuing JWT.
      (`db/ddl.sql`, `auth.py` pbkdf2+PyJWT, `routers/auth.py` login/me, seeded demo operator.)
- [x] 1.2 `require_operator()` dependency; protect inspections/crew/approve/WS; company scoping.
      (`auth.py:require_operator`, `routers/inspections.py` Depends + WS `?token=`.)
- [x] 1.3 Repository read methods take `company_id`; WS delivers only tenant events.
      (`repository.py` list/get/list_crew company filter + card company_id; `ws.py` per-tenant fan-out.)
- [x] 1.4 Twilio webhook signature verification. (`routers/whatsapp.py:verify_twilio_signature`)
- [x] 1.5 SSRF guard on media fetch (Twilio host allowlist). (`services/media_storage.py:_host_allowed`)
- [ ] 1.6 Private R2 + signed-URL route for media/PDF; remove public-bucket assumption.
      (Deferred to Phase 2 media/PDF work; demo runs on stub media locally.)
- [x] 1.7 Exact CORS origin, security headers, and per-service startup credential validation.
      (`main.py:validate_startup_config` + `security_headers`; single worker in `Procfile`.)

Verified: `pytest -q` = 28 passed (added auth-required + WS-token-reject tests).

## Phase 2 — Core correctness (R1, R4–R12, N1)
- [ ] 2.1 `inbound_events` table + MessageSid dedupe; make webhook processing idempotent.
      (Deferred: crediting now happens on the single operator-approve action and is idempotent,
      so duplicate WhatsApp delivery can't double-pay. Still worth adding post-demo.)
- [ ] 2.2 Durable job path + `PROCESSING`/`FAILED` states (post-demo; single worker for demo).
- [ ] 2.3 Redis-backed onboarding store + WebSocket pub/sub (post-demo, D3).
- [x] 2.4 Real CRM dispatch on approval: resolves company webhook, includes the card+pdf_url,
      `raise_for_status` → delivered/failed/skipped, persists `crm_status`, broadcasts
      `inspection.updated`. (`routers/inspections.py:approve_and_push`, `services/real.py:dispatch_crm`)
- [x] 2.5 Bounty credited exactly once on approval, guarded (PENDING→APPROVED); idempotent.
      (`repository.py:approve_inspection` — atomic `WHERE bounty_status='PENDING'`.)
- [x] 2.6 Location: GPS-pin parsed from Twilio → live reverse-geocode (OpenStreetMap free, or
      Mapbox if token) → real address confirmed. New-jobsite path auto-creates a jobsite from
      the confirmed GPS (option B). Existing jobsite: GPS corrects its address. No hard-coded Dallas.
- [x] 2.7 Photo intake wired into State 3: one-at-a-time instruction; per-photo CV QA on arrival
      (silent on good, specific callout on blurry/dark/duplicate; bad/dupes not counted); 45s
      quiet-timer + 20s grace → "still sending?" nudge → auto-advance to voice (no skip button);
      late photo re-opens & appends; max 8 auto-advances. `services.ingest_photo` (download→QA→R2).
      Single-worker in-memory timer — durable scheduler is a post-hosting upgrade.
- [ ] 2.8 Explicit State 5 confirmation with prerequisite checks.
- [~] 2.10 VISION best-photo selection BUILT + TESTED (`services/vision.py`, `RoofVision`):
      per-photo roof/damage/quality/claim-relevance assessment + `select_best` ranking, via
      Fireworks vision model `glm-5p3-flash` (VISION_MODEL, swappable). Real inference verified
      (correctly rejected a non-roof image); offline ranking test in `tests/test_vision.py`.
      Two-layer design: CV gate (photo_qa) → vision selection. TODO: wire into State 3 +
      build a labeled field-photo eval set before trusting it unattended (operator confirms).
- [x] 2.11 PDF fallback (`services/pdf.py` + `RealServices.compile_pdf`): when MODAL_API_URL
      is unset, render the supplement PDF locally (fpdf2) and store in R2 — verified live
      (real %PDF served from r2.dev). Lets the WhatsApp Submit complete before Modal exists.
- [x] 2.9 Extended inspection contract: `created_at`, `voice_note_url`, `supplement_value`,
      `crm_status` on both InMemory + Pg cards and the session model/schema.

Verified: `pytest -q` = 28 passed (bounty-once + CRM-status + idempotency tests added).

## Phase 3 — Frontend consolidation (R11, R12)
- [x] 3.1 Route only the FastAPI inspection plane (Live Feed / Claims / Crew Manager).
      Supabase legacy pages/hooks quarantined — unrouted, unimported, tree-shaken from the
      bundle. (Files remain on disk; deletion is optional post-demo cleanup.)
- [x] 3.2 Login UI + auth guard + token on API/WS. (`lib/auth.ts`, `lib/api.ts` Bearer +
      `inspectionsWsUrl` `?token=`, `components/auth/LoginScreen.tsx`, `App.tsx` gate; 401 → re-login.)
- [x] 3.3 Timestamp + audio player + supplement value in the drawer; removed fabricated
      `PAID` — approval reflects server `bounty_status`/`crm_status` (+ WS `inspection.updated`).
- [~] 3.4 Login error + existing empty states done; dialog `role`/focus-trap + keyboard-activable
      claims rows still TODO (a11y polish).
- [x] 3.5 Branding fixed: `package.json` → `codeverity-console`, `index.html` title/favicon,
      sidebar + login logo/labels → CodeVerity, "Sign out".

Verified: `npm run build` (tsc -b + vite build) green — 57 modules, no type errors.
Demo login (seeded): operator@apex.test / demo-password.

## Phase 4 — Operations & quality (N5, N6)
- [~] 4.1 Structured stdout logging at `LOG_LEVEL` + startup logging done. Error reporting
      (Sentry) + correlation IDs still TODO (post-demo).
- [x] 4.2 Readiness returns 503 (not 500) when the DB is down (`/readyz`); `/healthz` liveness.
      External-dependency probes + metrics/alerts are post-demo.
- [ ] 4.3 Integration tests (PgRepository, Modal, Twilio signature, CRM) + frontend tests — post-demo.
- [x] 4.4 CI (`.github/workflows/ci.yml`): backend ruff + pytest, frontend build + lint.
      `backend/requirements-dev.txt` pins pytest + ruff. (Activates once the repo is on GitHub.)
- [x] 4.5 `docs/RUNBOOK.md`: health, migrations, backup/restore, incidents, bounty safety, SLOs.

Verified: backend `ruff check app` clean + `pytest -q` = 28 passed; frontend `npm run build`
and `npm run lint` both green (legacy Supabase plane deleted — 23 files removed).

## Suggested execution order
0.4 → 0.5 → 0.6 → 1.4 → 1.5 → 1.7 → 1.1 → 1.2 → 1.3 → 1.6 → 2.1 → 2.5 → 2.4 → 2.2 → 2.3 →
2.6 → 2.7 → 2.8 → 2.9 → 3.x → 4.x.
Rationale: cheapest high-impact security first (signature/SSRF/CORS), then auth, then the
money/idempotency correctness, then the rest.
