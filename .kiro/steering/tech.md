# Tech — Stack, Commands, Conventions

## Stack
- **Backend:** Python 3.12, FastAPI, Uvicorn, Pydantic v2, asyncpg (Neon Postgres).
- **Frontend:** React 19 + TypeScript + Vite + Tailwind (operator console).
- **Media/PDF:** Cloudflare R2 (S3-compatible), Modal.com (`fpdf2`) PDF microservice.
- **AI:** Deepgram Nova-2 (STT), Fireworks.ai Llama-3.3-70B via `instructor`.
- **Geo:** Mapbox reverse geocoding.
- **Messaging:** Twilio WhatsApp Content API.
- **Hosting:** Heroku/Railway (backend), Vercel (frontend).

## Commands (Windows / pwsh)
Backend (from `backend/`):
```powershell
python -m venv .venv; .\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m app.db.migrate      # create/verify tables
python -m app.db.seed         # optional demo data
uvicorn app.main:app --reload --port 8000
pytest -q                     # 26 offline tests (stub services)
```
Frontend (from `frontend/`):
```powershell
npm install
npm run dev
npm run build
npm run lint
```

## Conventions
- Services follow a Protocol + Real/Stub pattern. Keep the stub path working so the
  app boots offline, but production selection must validate ALL required credentials
  for a real service — no "real Twilio + stub PDF" mixed modes.
- Repository is a Protocol with InMemory (tests) and Pg (prod) implementations.
- Treat all external input as untrusted: Twilio webhook bodies, media URLs, LLM output.
- Money/state transitions go through the repository in a single transaction and must
  be idempotent (guard on current status; dedupe on Twilio MessageSid).
- Pin dependencies. Add a dev-requirements file for pytest/lint rather than relying
  on ambient installs.

## Known production gaps (see spec before "finishing" a feature)
- CRM dispatch is currently a no-op (passes `None`).
- Bounty is credited at submission, not approval, and is not idempotent.
- Location/geocode/municipal-code lookup is stubbed; PDF address/citation hard-coded.
- No operator auth / tenant scoping on REST or WebSocket.
- Twilio webhook signature is not verified; R2 media is public.
- Documented 2-worker deploy breaks in-memory onboarding and WS fan-out.
