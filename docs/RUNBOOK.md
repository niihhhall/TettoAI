# CodeVerity Operations Runbook

Companion to `DEPLOYMENT.md`. Covers day-2 operations: health, migrations, backup/restore,
incidents, and target SLOs.

## Health & readiness
- `GET /healthz` → `{"status":"ok"}` — process is up (no dependency check).
- `GET /readyz` → `200 {"db":true}` when Postgres is reachable, else `503 {"db":false}`.
  Point the platform health check and uptime monitor at `/readyz`.

## Logs
- Structured stdout logging at `LOG_LEVEL` (default INFO). On Heroku/Railway, view with the
  platform log stream. Startup logs env + whether real services are active.
- What to grep during an incident: `readiness check failed`, `Startup config issues`,
  CRM `failed` statuses (visible in the console per inspection).

## Database (Neon)
- **Migrate:** `python -m app.db.migrate` (idempotent; run on deploy via the `release` phase).
- **Seed demo data:** `python -m app.db.seed` (idempotent for companies/crew/operators;
  jobsites are appended — do NOT run repeatedly in production).
- **Backup:** enable Neon point-in-time restore (branch/restore). Before a risky migration,
  create a Neon branch as a snapshot.
- **Restore:** restore the Neon branch to a timestamp, repoint `DATABASE_URL`, redeploy.
- **Migration policy:** forward-only. New columns via `ADD COLUMN IF NOT EXISTS`. Never drop
  a column in the same release that stops writing it.

## Common incidents
| Symptom | Likely cause | Action |
|--------|--------------|--------|
| `/readyz` 503 | Neon unreachable / bad `DATABASE_URL` | Check Neon status + env var; redeploy |
| Startup crash in prod | `validate_startup_config` (missing `JWT_SECRET`, wildcard CORS, real-services deps missing) | Read the error; set the named env var |
| Webhook 403s | Twilio signature mismatch / wrong `PUBLIC_BASE_URL` | Verify `PUBLIC_BASE_URL` matches the public URL Twilio calls |
| CRM shows `failed` | Company `crm_webhook_url` wrong/down | Fix webhook; operator re-approves to retry |
| Live feed not updating | WS dropped / token expired | Client auto-reconnects; if 1008, re-login |

## Bounty & money safety
- Bounty is credited exactly once, only on operator approval (`approve_inspection` is guarded
  on `bounty_status='PENDING'`). A repeated approve is a no-op. Reconcile payouts from the
  Crew Manager bounty ledger / payout CSV.

## Target SLOs (initial)
- Webhook ACK: p95 < 500 ms (fast empty-TwiML; heavy work is async).
- API read (inspections/crew): p95 < 300 ms.
- Availability: 99.5% for `/readyz` (demo/early-tenant target).
- CRM delivery success: > 98% of approvals (retry failures manually until auto-retry ships).

## Known post-demo hardening (tracked in `.kiro/specs/production-hardening/tasks.md`)
Private R2 + signed URLs (1.6), MessageSid idempotency (2.1), durable job queue +
PROCESSING/FAILED (2.2), Redis-backed multi-worker (2.3), live GPS geocode (2.6), photo
validation (2.7), explicit confirmation state (2.8), console a11y polish (3.4),
error reporting/metrics + integration/frontend tests (Phase 4 remainder).
