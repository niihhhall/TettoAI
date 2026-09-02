# Spike: Twilio WhatsApp Interactive Messaging (CodeVerity De-Risk)

**Purpose:** Prove the highest-risk integration in the CodeVerity PRD before building the
real backend — sending WhatsApp interactive messages (quick-reply buttons + list pickers)
via the Twilio Content API and correctly routing the inbound button/list replies through
a state machine.

This spike is **runnable and testable without a live Twilio account** (the sender is
mockable). Real scripts are included for when you wire in your credentials.

---

## Verified facts (Twilio docs, 2025–2026)

| Finding | Implication for CodeVerity |
|--------|-----------------------------|
| Quick-reply buttons can be sent **in-session without template approval** | States 2/3/4 work with zero approval latency |
| In-session unapproved quick replies are capped at **3 buttons** | PRD already designed to 3 — compliant |
| The tapped button returns our developer-defined `id` in the **`ButtonPayload`** webhook field | Deterministic state routing (no fragile text matching) |
| **List pickers cannot initiate** a session and can't be approval-submitted | States 0.5/1 only work after the foreman messages first |
| Messages outside the **24-hour session window** require a pre-approved template | Need a session tracker + re-engagement template library |
| `wa.me/<number>?text=...` click-to-chat links open a chat with prefilled text | This is the QR/sticker entry point that opens the session |

Sources: Twilio `twilio/quick-reply`, `twilio/list-picker`, "Using Buttons in WhatsApp",
"Session Definitions", error 63016 docs.

---

## What this spike proves

1. **Send path** — construct valid Content API template-creation payloads and send
   messages by `ContentSid` + `ContentVariables`.
2. **Receive path** — parse a real Twilio inbound webhook form body and extract
   `ButtonPayload` / list selection.
3. **State routing** — a tapped button deterministically drives the next state.
4. **Fast ACK** — the webhook returns an empty `<Response/>` TwiML immediately
   (PRD §3.1), doing zero heavy work inline.
5. **24h window guard** — detect when we're out-of-session and must fall back to an
   approved template.

## Files

| File | Role |
|------|------|
| `main.py` | FastAPI webhook: fast empty-TwiML ACK + state routing on `ButtonPayload` |
| `whatsapp_client.py` | Send helpers (real Twilio SDK or in-memory outbox for tests) |
| `content_templates.py` | Defines + (optionally) creates the CodeVerity Content templates |
| `session_window.py` | 24-hour session-window tracker |
| `test_spike.py` | Pytest: simulates inbound webhooks, asserts routing + ACK shape |
| `.env.example` | Required environment variables |

## Run it

```powershell
# from spike/twilio-whatsapp
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt

# 1. Run the offline test harness (NO Twilio account needed)
pytest -v

# 2. Run the webhook locally
uvicorn main:app --reload --port 8000

# 3. (Optional, needs real creds) create the Content templates in your Twilio account
#    Copy .env.example -> .env and fill in creds, then:
python content_templates.py --create
```

To test end-to-end with real WhatsApp, expose port 8000 with a tunnel (e.g. ngrok) and
set that URL as the inbound webhook on your Twilio WhatsApp sender / sandbox.
