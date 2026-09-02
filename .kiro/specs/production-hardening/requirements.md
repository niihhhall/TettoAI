# Requirements — Production Hardening

Status: CONFIRMED (decisions locked; optimizing for demo-ready build)
Governing baseline: `docs/kiro-production-prd-v4.md` (owner-selected; v2 superseded)

## Goal
Take the working CodeVerity skeleton to a production-grade system that a real
contractor tenant can use end-to-end: a foreman submits over WhatsApp, an operator
reviews and pushes to CRM, and a foreman is paid exactly once on approval — safely,
observably, and recoverably.

## Decisions (CONFIRMED by owner)
- **D1 CRM push model:** operator-approved push only for now; automated webhook-driven
  push is the documented future path. Canonical target: JobNimbus generic webhook.
- **D2 Manufacturer warranty proof:** deferred; demo triangulation = photo + municipal ordinance.
- **D3 Worker topology:** single web worker for the demo (no Redis dependency to stand up);
  Redis-backed onboarding + WS pub/sub is a post-demo fast-follow for horizontal scale.
- **D4 Operator auth:** email + password (hashed) + short-lived JWT, company-scoped. The
  frontend already ships a login UI (owner-built) to be wired to this backend.
- **D5 Language:** English-only; `preferred_language` out of scope.
- **Frontend:** owner-built dashboard (with operator login) is integrated into this repo
  as the single production console; the inherited Supabase legacy plane is removed.
- **D6 Vision / photo intelligence:** two-layer design — CV gate (`photo_qa`) + vision model
  (`vision.py`, `glm-5p3-flash`) for best-claim-photo selection. Runs as operator decision-support.
  DEMO: describe + optionally show live on a sample roof image (no client photos yet).
  POST-DEMO: collect ~20-30 real client photos to use as an EVAL SET + few-shot calibration +
  threshold tuning — NOT fine-tuning (too few to fine-tune; fine-tuning only if eval proves the
  base model + prompting is insufficient, and would require a much larger labeled set).

## Functional requirements (EARS-style)

### Identity & tenancy
- R1 WHEN an inbound WhatsApp message arrives THE SYSTEM SHALL resolve the sender by
  E.164 before any AI step and load the crew + company context.
- R2 THE SYSTEM SHALL scope every operator read/write and CRM action to the caller's
  company; no endpoint SHALL return cross-tenant data.
- R3 WHEN an operator authenticates THE SYSTEM SHALL issue a company-scoped session and
  reject unauthenticated access to inspection/crew/approve/WebSocket endpoints.

### Intake correctness (states 0–6)
- R4 WHEN a foreman sends a GPS pin or location THE SYSTEM SHALL parse coordinates,
  reverse-geocode to address + city + county, persist them, and fetch/store the
  municipal code summary. No PDF field SHALL be hard-coded.
- R5 WHEN photos are uploaded THE SYSTEM SHALL validate content type, enforce the
  configured min/max count, store to private media, and record them on the session.
- R6 WHEN a voice note is received THE SYSTEM SHALL transcribe (English) and extract
  structured Xactimate line items; on extraction failure it SHALL record a FAILED
  state and notify the foreman, never silently drop the work.
- R7 THE SYSTEM SHALL have an explicit confirmation step (State 5) that requires the
  prerequisites (location + at least the min photos + line items) before submission.

### Bounty & CRM (money)
- R8 THE SYSTEM SHALL credit a foreman's $25 bounty exactly once, only on operator
  approval, moving status PENDING → APPROVED → PAID.
- R9 WHEN the same Twilio MessageSid is delivered more than once THE SYSTEM SHALL
  process it at most once (idempotent).
- R10 WHEN an operator approves an inspection THE SYSTEM SHALL resolve the company CRM
  webhook, POST the package including the PDF URL, verify a success status, persist the
  delivery result, and reflect it durably to the console (no fabricated client state).

### Realtime console
- R11 THE SYSTEM SHALL deliver inspection snapshots and completion events to all
  connected operators of the tenant regardless of which web worker handles them.
- R12 THE inspection contract SHALL include created_at timestamp, voice note URL
  (for the audio player), and supplement value.

## Non-functional requirements
- N1 Webhook ACK returns empty TwiML in well under the Twilio timeout; heavy work runs
  off the request path with durable retry (not fire-and-forget in-process).
- N2 All secrets from environment; production service selection validates every
  required credential for that service or fails fast at startup.
- N3 Twilio webhook signature verified; media fetches restricted to Twilio hosts
  (SSRF guard); CORS restricted to the exact console origin; security headers set.
- N4 Claim photos/audio/PDFs are private, served via short-lived signed URLs.
- N5 Structured logs + error reporting + real health/readiness; key flows emit metrics.
- N6 Migrations are forward-only and idempotent; a documented backup/restore path exists.

## Acceptance criteria (definition of "production-grade" for MVP)
- A tenant operator logs in and sees only their company's inspections.
- A full WhatsApp intake with a real GPS pin produces a real address + municipal code
  and a PDF with no hard-coded values.
- Approving an inspection pushes to a live CRM webhook and durably records success/failure.
- A foreman is credited exactly once, on approval, verified under duplicate delivery.
- No unauthenticated access to PII/money endpoints; Twilio signature enforced; media private.
- CI runs backend + frontend build/lint/tests on every push; integration tests cover the
  CRM push, bounty idempotency, and location/geocode paths.

## Out of scope (this spec)
Multi-language voice, manufacturer-warranty sourcing, homeowner/insurer surfaces,
billing/subscription, and the inherited Supabase sales-agent product (to be removed).
