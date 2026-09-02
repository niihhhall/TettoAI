# Structure — Repo Layout & Boundaries

## Top level
```
tetto-mvp/
├── .kiro/                  # steering + specs (version-controlled)
├── backend/               # FastAPI app, state machine, services, DB
├── frontend/              # React operator console (has its own nested .git today)
├── modal_worker/          # Modal.com PDF microservice
├── spike/twilio-whatsapp/ # de-risk spike (reference, not production)
└── docs/                  # PRD + deployment guide
```

## Backend layout (`backend/app/`)
- `main.py` — app startup, runtime wiring, CORS, health/readiness, router mounts.
- `config.py` — Settings (env). `deps.py` — Runtime container + `get_runtime()`.
- `routers/whatsapp.py` — Twilio webhook: fast TwiML ACK + BackgroundTasks handoff.
- `routers/inspections.py` — operator REST + `/ws/inspections` WebSocket.
- `whatsapp/state_machine.py` — states 0–6 (the field-intake control flow).
- `whatsapp/client.py`, `templates.py` — Twilio send + Content templates.
- `services/` — media_storage (R2), speech (Deepgram), code_extractor (Fireworks),
  geocoding (Mapbox), real.py (RealServices), __init__.py (StubServices).
- `repository.py` — Repository Protocol + InMemory + Pg implementations.
- `models.py` — dataclasses + State enum. `db/` — pool, ddl.sql, migrate, seed.
- `ws.py` — ConnectionManager (currently process-local).

## Frontend layout (`frontend/src/`)
- Real CodeVerity plane: `pages/Conversations.tsx` (Live Feed), `pages/Leads.tsx`
  (Claims), `pages/Instances.tsx` (Crew Manager), `components/inspections/InspectionDrawer.tsx`,
  `hooks/useInspections.ts`, `hooks/useCrew.ts`, `lib/api.ts`.
- Legacy inherited plane (MarkEye/After5, Supabase): Overview/Bookings/Training/
  Performance and most `components/leads`, `components/agent`, `useLeads`, `useMessages`,
  `lib/supabase.ts`. Being quarantined/removed — do not extend it.

## Boundary rules
- Feature logic lives in its owning layer; the state machine talks to storage only
  through the Repository Protocol and to the world only through Services.
- The operator API is the single production data plane for the console. New console
  features use the FastAPI inspection contract, not Supabase.
- Cross-service contracts (PDF payload, WS events, inspection card shape) are shared
  and must change on both sides together.

## Git note
The workspace root is not yet a git repo; only `frontend/` is (remote:
markeye-agenticui). Consolidation strategy is an open decision in the spec — do not
run destructive git operations on `frontend/.git` without explicit approval.
