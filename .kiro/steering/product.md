# Product — CodeVerity Field & Operator System

## What this is
Autonomous field-intake and supplement-orchestration infrastructure for US
residential storm-restoration roofing contractors. 1099 foremen submit photos
and a voice note over WhatsApp (zero typing on the roof); the backend transcribes,
extracts Xactimate line items, compiles a supplement PDF, and surfaces it to an
office operator who reviews and pushes it to the contractor's CRM. Foremen earn a
$25 bounty per approved package.

## Canonical requirements source
`docs/kiro-production-prd-v4.md` is the governing baseline (owner decision: v4 is the
latest and now lives in `docs/`). `docs/kiro-production-prd-v2.md` is superseded but kept
for history. `docs/DEPLOYMENT.md`, `spike/twilio-whatsapp/README.md`, and
`modal_worker/README.md` are addenda. The v4 export features (PDF / Claims CSV / Bounty
payout CSV) ARE in demo scope.

Production-hardening work is tracked in `.kiro/specs/production-hardening/`.
Current objective: a working, credible DEMO build first (correct + secure enough to show
a client), then per-tenant rollout.

## Primary personas
- **Field foreman (1099 subcontractor):** on a roof, phone-only, WhatsApp, no typing.
  Goal: submit evidence fast, earn the $25 bounty on approval.
- **New/unregistered worker:** onboards via name + company invite code.
- **Office operator / estimator:** desktop console. Reviews inspections, copies
  Xactimate line items, approves and pushes to CRM.
- **Contractor company (tenant):** owns crew, jobsites, invite code, and CRM config.
- **Deployment operator (you):** provisions and runs the stack.

## Core principles (must survive every change)
1. Zero-friction field intake (buttons/lists/GPS/voice; minimize typing).
2. Database-first identity (E.164 lookup before any AI step).
3. Decoupled async processing (fast webhook ACK; heavy work off the request path).
4. Evidence-backed line items (photo + municipal ordinance; manufacturer proof is post-MVP unless a spec says otherwise).
5. Bounty is EARNED on office approval, not on field submission.

## Money & trust rules
- Bounty state must move PENDING → APPROVED → PAID with exactly-once crediting.
- Every foreman/inspection/CRM action is tenant-scoped; no cross-company access.
- Claim photos, audio, and PDFs are private; never a public bucket.

## Non-goals (for the current MVP unless re-scoped)
- Multi-language voice (English-only MVP).
- Manufacturer-warranty auto-sourcing.
- Homeowner/insurer-facing surfaces.
