<div align="center">

# 🏠⚡ TettoAI

### Autonomous field-intake & supplement-orchestration infrastructure for storm-restoration roofing

**Foremen shoot photos and talk. The system transcribes, extracts Xactimate line items, builds the supplement PDF, and drops it on an operator's desk — CRM-ready.**

<br/>

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-async-009688?logo=fastapi&logoColor=white)
![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)
![TypeScript](https://img.shields.io/badge/TypeScript-Vite-3178C6?logo=typescript&logoColor=white)
![Postgres](https://img.shields.io/badge/Neon-Postgres-336791?logo=postgresql&logoColor=white)
![WhatsApp](https://img.shields.io/badge/WhatsApp-Cloud%20API-25D366?logo=whatsapp&logoColor=white)
![Deployed on Render](https://img.shields.io/badge/Backend-Render-46E3B7?logo=render&logoColor=white)
![Vercel](https://img.shields.io/badge/Console-Vercel-000000?logo=vercel&logoColor=white)

<em>Zero typing on the roof · Database-first identity · Evidence-backed line items · Bounty on approval</em>

</div>

---

## 📖 Table of Contents

- [What it is](#-what-it-is)
- [Why it matters](#-why-it-matters)
- [How it works](#-how-it-works)
- [Feature highlights](#-feature-highlights)
- [Architecture](#️-architecture)
- [Tech stack](#-tech-stack)
- [Repo layout](#-repo-layout)
- [Quick start](#-quick-start)
- [Configuration](#-configuration)
- [Tests](#-tests)
- [Security & trust](#-security--trust)
- [Deployment](#-deployment)
- [Roadmap](#️-roadmap)

---

## 🎯 What it is

TettoAI (internally the **CodeVerity Field & Operator System**) is production infrastructure for US residential storm-restoration roofing contractors.

A 1099 field foreman, standing on a roof with only a phone, sends photos and a voice note over **WhatsApp** — no apps, no typing, no forms. The backend then:

1. **Identifies** the foreman by phone number before any AI runs (database-first identity).
2. **Transcribes** the voice note (Deepgram Nova-2, tuned with roofing trade vocabulary).
3. **Captions** each photo for damage type and building-code relevance (vision model).
4. **Extracts** structured Xactimate line items (Fireworks LLM via `instructor`).
5. **Compiles** a supplement PDF with photo evidence and the municipal code citation.
6. **Surfaces** the package live to an office operator, who reviews and pushes it to the contractor's CRM.

The foreman earns a **$25 bounty per approved package** — credited on office approval, never on submission.

## 💡 Why it matters

Supplement documentation is where restoration revenue leaks. Foremen hate paperwork; estimators drown in half-captured jobs. TettoAI turns a two-minute WhatsApp exchange into a defensible, evidence-linked supplement — while the crew is still on the roof.

| Principle | What it guarantees |
|-----------|-------------------|
| 🚫 **Zero-friction field intake** | Buttons, lists, GPS pins, and voice — typing is minimized to near zero |
| 🆔 **Database-first identity** | E.164 phone lookup happens before any AI step |
| ⚡ **Decoupled async processing** | Webhook ACKs in milliseconds; heavy work runs off the request path |
| 📸 **Evidence-backed line items** | Every line item links to the photo + municipal ordinance that supports it |
| 💵 **Bounty earned on approval** | `PENDING → APPROVED → PAID`, credited exactly once |

---

## 🎬 How it works

<div align="center">

```
   📱 Foreman (WhatsApp)                    🖥️  Operator Console
   ─────────────────────                    ────────────────────
   "hi"  ───────────────►  identify + open session
   [pick jobsite]                                  │
   [share GPS pin]  ────►  reverse-geocode + code   │
   📷 photo + 🎙️ voice  ─►  CV quality-gate, store   │  ◄── live feed (WebSocket)
   📷 photo + 🎙️ voice     transcribe + caption      │
   [Continue]  ─────────►  extract Xactimate items   │
   [Submit package]  ──►   compile PDF ──────────────┼──►  📄 review drawer
                                                      │     1-click Xactimate copy
                           bounty PENDING ◄───────────┤     ✅ Approve → CRM push
                           bounty APPROVED  ──────────┘     💵 bounty credited
```

</div>

The intake is a deterministic **state machine (states 0–6)** driven off WhatsApp button/list payloads, so the on-roof flow is predictable and testable. Photos are collected one at a time with an optional voice note each; the step auto-advances after the foreman stops sending.

---

## ✨ Feature highlights

- **WhatsApp-native intake** — Meta WhatsApp Cloud API (default) or Twilio, behind one provider-agnostic sender.
- **Idempotent webhooks** — inbound messages are deduped on the provider message id, so at-least-once retries never double-send a welcome or double-process a step.
- **Computer-vision photo QA** — blur/dark/blown-out/duplicate detection rejects unusable shots before they hit storage.
- **Roofing-tuned transcription** — Deepgram Nova-2 biased toward `drip edge`, `sheathing`, `ice and water shield`, `Xactimate`, and the rest of the trade vocabulary.
- **Structured extraction** — Fireworks LLM + `instructor` turns free-form voice notes into typed Xactimate line items, each linked back to its supporting photos.
- **Live operator console** — React 19 + Vite: Live Feed, Claims table, Crew Manager, and an inspection drawer with the PDF and one-click Xactimate copy, streamed over WebSocket.
- **Multi-tenant by design** — every foreman, inspection, and CRM action is scoped to a contractor company.
- **Boots offline** — with no external credentials the app falls back to an in-memory sender and deterministic stub services, so the full flow and dashboard work locally.

---

## 🏗️ Architecture

```
                         ┌──────────────────────────────┐
   📱 Field Crew         │  Meta WhatsApp Cloud API       │
   (WhatsApp) ──────────►│  (or Twilio) — fast webhook ACK│
                         └───────────────┬────────────────┘
                                         │  BackgroundTask handoff
                                         ▼
        ┌────────────────────────────────────────────────────────────┐
        │  FastAPI backend  ·  Render  ·  single worker                │
        │  ── state machine (0–6) · repository · services ──           │
        └───┬───────┬───────┬───────┬───────┬───────┬─────────────────┘
            │       │       │       │       │       │
            ▼       ▼       ▼       ▼       ▼       ▼
        Neon    Cloudflare  Deepgram  Fireworks  Mapbox   Modal.com
        Postgres    R2      Nova-2    (Llama/GPT  geocode  fpdf2 PDF
        identity  media/PDF  STT      + vision)            microservice
        + state
            │
            │  REST + WebSocket (live inspection cards)
            ▼
   🖥️  Operator Console — React 19 + Vite (Vercel)
       Live Feed · Claims · Crew Manager · Inspection drawer
```

**Design contracts**
- Services follow a **Protocol + Real/Stub** pattern — production selection validates *all* required credentials for a real service (no mixed real/stub modes).
- Storage is a **Repository Protocol** with `InMemory` (tests) and `Pg` (prod) implementations.
- Money and state transitions go through the repository in a single, idempotent transaction.
- All external input — webhook bodies, media URLs, LLM output — is treated as untrusted.

---

## 🧱 Tech stack

| Layer | Technology |
|-------|-----------|
| **Backend** | Python 3.12 · FastAPI · Uvicorn · Pydantic v2 · asyncpg |
| **Database** | Neon (serverless Postgres) |
| **Frontend** | React 19 · TypeScript · Vite · Tailwind CSS |
| **Messaging** | Meta WhatsApp Cloud API (default) · Twilio WhatsApp |
| **Speech-to-text** | Deepgram Nova-2 |
| **LLM / extraction** | Fireworks.ai (Llama / GPT-OSS) via `instructor` |
| **Vision** | Fireworks vision model (photo damage assessment) |
| **Media / PDF** | Cloudflare R2 (S3-compatible) · Modal.com (`fpdf2`) |
| **Geocoding** | Mapbox (with free OpenStreetMap fallback) |
| **Hosting** | Render (backend) · Vercel (console) |

---

## 📂 Repo layout

| Path | What lives here |
|------|-----------------|
| `backend/` | FastAPI app: WhatsApp webhooks + state machine (0–6), services, WebSocket, REST, DB |
| `backend/app/whatsapp/` | State machine, provider clients (Meta/Twilio), templates, webhook dedup |
| `backend/app/services/` | R2 storage, Deepgram STT, Fireworks extractor, vision, geocoding, photo QA, PDF |
| `modal_worker/` | Modal.com serverless PDF microservice (`fpdf2`) |
| `frontend/` | React 19 + Vite operator console |
| `docs/` | Governing PRD (`kiro-production-prd-v4.md`), `DEPLOYMENT.md`, `RUNBOOK.md` |
| `.kiro/` | Steering, specs, and production-hardening tracking |

---

## 🚀 Quick start

### Backend

```powershell
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env        # fill DATABASE_URL at minimum
python -m app.db.migrate      # create/verify tables in Neon
python -m app.db.seed         # optional demo data (Apex 4821, Titan 7710)
uvicorn app.main:app --reload --port 8000
```

> With no external credentials the app still boots — it uses an in-memory sender and
> deterministic stub services, so the state machine and dashboard work end-to-end locally.

### Frontend

```powershell
cd frontend
npm install
copy .env.example .env         # set VITE_API_URL=http://localhost:8000
npm run dev
```

Then open the console at **http://localhost:5173** and the API at **http://localhost:8000** (health check: `/healthz`, readiness: `/readyz`).

---

## 🔧 Configuration

All secrets come from environment variables — never hard-coded, never committed. Start from `backend/.env.example` and `frontend/.env.example`.

Key backend variables:

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Neon Postgres connection string (required) |
| `MESSAGING_PROVIDER` | `meta` (default) or `twilio` |
| `META_ACCESS_TOKEN` / `META_PHONE_NUMBER_ID` / `META_VERIFY_TOKEN` | WhatsApp Cloud API credentials |
| `R2_*` | Cloudflare R2 media/PDF storage |
| `DEEPGRAM_API_KEY` | Speech-to-text |
| `FIREWORKS_API_KEY` | Line-item extraction + vision |
| `MAPBOX_ACCESS_TOKEN` | Reverse geocoding (optional; free fallback otherwise) |
| `JWT_SECRET` | Operator session signing (required in production) |
| `CORS_ORIGINS` | Exact console origin(s) — locked down in production |

See **`docs/DEPLOYMENT.md`** for the full environment matrix across Neon, R2, the messaging provider, Modal, Render, and Vercel.

---

## 🧪 Tests

```powershell
cd backend
pytest -q
```

| Suite | Location | Notes |
|-------|----------|-------|
| **Backend** | `backend/` → `pytest -q` | 41 tests, fully offline (InMemory repo + stub services) |
| **PDF renderer** | `modal_worker/` → `pytest -q` | supplement PDF rendering |
| **Twilio spike** | `spike/twilio-whatsapp/` → `pytest -q` | reference de-risk spike |

Backend tests run with a dummy `DATABASE_URL` and no external calls, so they're deterministic and fast — including a regression test that drives the real photo quiet-timer.

---

## 🔒 Security & trust

- **Idempotent, deduped webhooks** — provider retries can't double-process a message.
- **SSRF-guarded media fetches** — inbound media URLs must be HTTPS and on an allowlisted host.
- **Signature verification** — Twilio `X-Twilio-Signature` and Meta `X-Hub-Signature-256` are validated when configured.
- **Security headers** — `X-Content-Type-Options`, `X-Frame-Options`, `Referrer-Policy`, and HSTS in production.
- **Tenant isolation** — foreman, inspection, and CRM actions are company-scoped.
- **Fail-fast startup** — production boot refuses wildcard CORS, a missing `JWT_SECRET`, or a real-service bundle with a missing dependency.

> ⚠️ **Never commit secrets.** `.env` files are gitignored; production credentials live only in the host's secret store (Render / Vercel dashboards). Rotate any credential that has been shared outside the secret store.

---

## 🚢 Deployment

The backend deploys to **Render** from `render.yaml` (single worker — in-memory onboarding state, WebSocket fan-out, and photo timers are process-local). The console deploys to **Vercel**. Full checklist and the environment-variable matrix are in **`docs/DEPLOYMENT.md`**, with operational procedures in **`docs/RUNBOOK.md`**.

## 🗺️ Roadmap

Production-hardening work is tracked in `.kiro/specs/production-hardening/`. Highlights:

- [ ] Durable, shared idempotency + onboarding store (Redis / Postgres) for multi-worker scale
- [ ] Bounty credited exactly-once on approval across the full state transition
- [ ] Live municipal-code / geocode lookup wired into the supplement citation
- [ ] Operator auth + tenant scoping hardened across REST and WebSocket
- [ ] Private media buckets with signed URLs
- [ ] CRM dispatch on operator approval

---

<div align="center">

**TettoAI** — built for the roof, not the desk.

<sub>Governing spec: <code>docs/kiro-production-prd-v4.md</code></sub>

</div>
