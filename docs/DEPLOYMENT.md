# CodeVerity Deployment Guide

Deploy order matters — provision data + storage + microservice first, then the backend,
then the frontend, then point Twilio at the backend last.

```
Neon ─► Cloudflare R2 ─► Modal (PDF) ─► Backend (Heroku/Railway) ─► Vercel (frontend) ─► Twilio webhook
```

---

## 1. Neon Postgres

1. Create a Neon project; copy the pooled connection string (ends with `?sslmode=require`).
2. This becomes `DATABASE_URL`. The backend's `normalize_dsn()` strips `sslmode` and applies
   TLS itself (asyncpg doesn't accept `sslmode` in the DSN).
3. Tables are created by the backend release step (`python -m app.db.migrate`), which is
   idempotent. Optionally seed demo data: `python -m app.db.seed`.

## 2. Cloudflare R2

1. Create a bucket (e.g. `codeverity-media`) and an R2 API token (Access Key + Secret).
2. Enable public access via a custom domain (e.g. `cdn.codeverity.ai`) so photo/audio/PDF
   URLs are publicly fetchable by WhatsApp and the console.
3. Record `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`, `R2_BUCKET_NAME`,
   `R2_PUBLIC_CUSTOM_DOMAIN`.

## 3. Modal PDF microservice

```bash
pip install modal && modal token new
modal secret create codeverity-r2 \
  R2_ENDPOINT_URL=... R2_ACCESS_KEY_ID=... R2_SECRET_ACCESS_KEY=... \
  R2_BUCKET_NAME=codeverity-media R2_PUBLIC_CUSTOM_DOMAIN=cdn.codeverity.ai
modal deploy modal_worker/pdf_service.py
```
Copy the printed endpoint URL → backend `MODAL_API_URL`.

## 4. Backend (Heroku or Railway)

Both read the `Procfile`:
```
web: uvicorn app.main:app --host 0.0.0.0 --port $PORT --workers 2
release: python -m app.db.migrate
```
- **Heroku:** `heroku create`, set config vars (below), `git push heroku main`. `runtime.txt`
  pins Python 3.12; the `release` phase runs the migration automatically.
- **Railway:** new service from the `backend/` dir; Nixpacks detects Python. Add the same
  variables. Run the migration once (Railway runs the Procfile `release` too).

Set **all** backend env vars from the matrix below. Set `CORS_ORIGINS` to your Vercel URL.
Verify: `GET /healthz` → `{"status":"ok"}`, `GET /readyz` → `{"db":true}`.

## 5. Frontend (Vercel)

1. Import the repo, set **Root Directory = `frontend`**.
2. Build command `npm run build`, output `dist` (Vite default). `vercel.json` provides the
   SPA rewrite so deep links work.
3. Env: `VITE_API_URL=https://<your-backend-host>` (WS URL is auto-derived http→ws/https→wss;
   override with `VITE_WS_URL` if needed).
4. Redeploy after setting env vars.

## 6. Twilio WhatsApp (do last)

1. In the Content Template Builder, create the 5 CodeVerity templates (see
   `backend/app/whatsapp/templates.py` / the spike's `content_templates.py --create`).
   Quick-reply templates stay **unsubmitted** (usable in-session without approval); the
   list-picker works only in an active 24h session.
2. Put the resulting ContentSids into the backend `CONTENT_SID_*` vars.
3. Set the WhatsApp sender's **inbound webhook** to
   `https://<your-backend-host>/api/v1/whatsapp/webhook` (HTTP POST).
4. Entry point for foremen: a `wa.me/<sender-number>?text=...` click-to-chat link (QR /
   truck sticker) — the foreman sending first opens the 24h window that unlocks buttons/lists.

---

## Environment variable matrix

| Variable | Backend | Modal | Vercel | Notes |
|----------|:------:|:----:|:-----:|-------|
| `DATABASE_URL` | ✅ | | | Neon pooled, `?sslmode=require` |
| `CORS_ORIGINS` | ✅ | | | Set to Vercel URL in prod |
| `TWILIO_ACCOUNT_SID` / `TWILIO_AUTH_TOKEN` | ✅ | | | Enables real WhatsApp sends |
| `TWILIO_WHATSAPP_FROM` | ✅ | | | `whatsapp:+<E164>` |
| `CONTENT_SID_*` (5) | ✅ | | | From Content Template Builder |
| `R2_ENDPOINT_URL` / `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` | ✅ | ✅ | | Media + PDF storage |
| `R2_BUCKET_NAME` / `R2_PUBLIC_CUSTOM_DOMAIN` | ✅ | ✅ | | Public CDN URLs |
| `DEEPGRAM_API_KEY` | ✅ | | | Nova-2 STT |
| `FIREWORKS_API_KEY` | ✅ | | | Llama-3.3-70B extraction |
| `MAPBOX_ACCESS_TOKEN` | ✅ | | | Reverse geocoding |
| `MODAL_API_URL` | ✅ | | | PDF endpoint from `modal deploy` |
| `VITE_API_URL` | | | ✅ | Backend base URL |
| `VITE_WS_URL` | | | ⬜ | Optional; else derived from `VITE_API_URL` |

The backend boots without the optional keys (falls back to stub services); it uses
`RealServices` only when R2 + Deepgram + Fireworks keys are all present.

## Post-deploy verification checklist

- [ ] `GET /healthz` and `/readyz` OK on the backend host.
- [ ] Neon shows the 4 tables (`companies`, `crew_members`, `jobsites`, `inspection_sessions`).
- [ ] Modal endpoint returns `{"pdf_url": ...}` for a sample payload.
- [ ] Vercel site loads; Live Feed shows "Live" (WebSocket connected).
- [ ] Send a WhatsApp message to the sender → webhook returns 200 fast → a reply arrives.
- [ ] Complete a full intake → inspection appears live in the console → PDF renders in the
      drawer → Approve & Push works.

## Production hardening notes (CTO flags)

- **CORS** is wildcard by default — set `CORS_ORIGINS` to the exact Vercel origin in prod.
- **Twilio webhook signature validation** is not yet enforced; add `X-Twilio-Signature`
  verification before going live to reject spoofed webhooks.
- **24h session window:** re-engaging a foreman after the window requires a pre-approved
  template (approval up to 48h). Submit those templates early.
- **Secrets:** never commit `.env`. The PRD's Section 8 sample keys should be treated as
  rotated/invalid.
