# CodeVerity — Field & Operator System

Autonomous field-intake and supplement-orchestration infrastructure for US residential
storm-restoration roofing contractors. 1099 foremen submit photos + a voice note over
WhatsApp (zero typing); the backend transcribes, extracts Xactimate line items, compiles a
supplement PDF, and pushes it to the contractor's CRM. Foremen earn a $25 bounty per
approved package.

Built per `docs/kiro-production-prd-v2.md`.

## Architecture

```
[Field Crew · WhatsApp]
        │  (Twilio webhook, <50ms empty-TwiML ACK)
        ▼
[FastAPI backend · Heroku/Railway] ──► [Neon Postgres]  (identity + state machine)
        │                          ──► [Cloudflare R2]   (photos/audio/PDF)
        │                          ──► [Deepgram Nova-2]  (STT)
        │                          ──► [Fireworks Llama-3.3-70B + instructor] (line items)
        │                          ──► [Mapbox]           (dual-layer city/county geofence)
        │                          ──► [Modal.com]        (fpdf2 PDF microservice)
        │  (WebSocket, 30s keep-alive)
        ▼
[Operator Console · React 19 + Vite on Vercel]
   Live Feed · Claims table · Crew Manager · Inspection drawer (PDF + 1-click Xactimate copy)
```

## Repo layout

| Path | What |
|------|------|
| `backend/` | FastAPI app: WhatsApp webhook + state machine (0–6), integrations, WebSocket, REST |
| `modal_worker/` | Modal.com serverless PDF microservice (`fpdf2`) |
| `frontend/` | React 19 + Vite operator console (repurposed `markeye-agenticui`) |
| `spike/twilio-whatsapp/` | De-risk spike proving Twilio interactive messaging round-trip |
| `docs/` | PRD + `DEPLOYMENT.md` |

## Local development

**Backend**
```powershell
cd backend
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env    # fill DATABASE_URL at minimum
python -m app.db.migrate  # create tables in Neon
python -m app.db.seed     # optional demo data (Apex 4821, Titan 7710)
uvicorn app.main:app --reload --port 8000
```
Without external credentials the app still boots: it falls back to an in-memory sender and
deterministic stub services, so the state machine and dashboard work end-to-end locally.

**Frontend**
```powershell
cd frontend
npm install
copy .env.example .env     # set VITE_API_URL=http://localhost:8000
npm run dev
```

## Tests

| Suite | Command (from dir) | Count |
|-------|--------------------|-------|
| Backend | `backend` → `pytest -q` | 26 |
| PDF renderer | `modal_worker` → `pytest test_renderer.py -q` | 3 |
| Twilio spike | `spike/twilio-whatsapp` → `pytest -q` | 12 |

Backend tests set a dummy `DATABASE_URL` and run fully offline (InMemory repo + stub services).

## Deployment

See **`docs/DEPLOYMENT.md`** for the full checklist and the environment-variable matrix
across Neon, Cloudflare R2, Twilio, Modal, the backend host, and Vercel.
