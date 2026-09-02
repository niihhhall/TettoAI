"""CodeVerity WhatsApp Content templates.

Defines the interactive templates for the field-intake state machine and can create them
in a real Twilio account via the Content API.

Key rules validated during de-risk:
  * quick-reply: <= 3 actions to remain sendable IN-SESSION without approval.
  * list-picker: cannot initiate a session and cannot be approval-submitted; only usable
    once the foreman is already in a 24h session.
  * Each action's `id` is what comes back in the inbound `ButtonPayload` field, so IDs are
    the contract between the UI and the state machine.

Run `python content_templates.py --create` (with creds in .env) to create them and print
the resulting ContentSids.
"""

from __future__ import annotations

import argparse
import json
import os

# Each template: friendly_name -> Content API "types" payload.
# The `id` values are the state-machine routing keys (returned as ButtonPayload).

TEMPLATES: dict[str, dict] = {
    # State 0.5 — company selection (list picker; only works in-session)
    "codeverity_company_list": {
        "twilio/list-picker": {
            "body": "Select your company or tap to enter a company code:",
            "button": "Select Company",
            "items": [
                {"id": "company_apex", "item": "Apex Roofing", "description": "Code: 4821"},
                {"id": "company_titan", "item": "Titan Storm Restoration", "description": "Code: 7710"},
                {"id": "enter_company_code", "item": "🔑 Enter Company Code", "description": "Type your code"},
            ],
        }
    },
    # State 1 — jobsite selection (list picker). {{1}}/{{2}} filled at send time.
    "codeverity_jobsite_list": {
        "twilio/list-picker": {
            "body": "Select the jobsite you're inspecting:",
            "button": "Select Jobsite",
            "items": [
                {"id": "job_1", "item": "{{1}}", "description": "{{2}}"},
                {"id": "new_jobsite", "item": "➕ New Jobsite", "description": "Start a new inspection"},
            ],
        }
    },
    # State 2 — location confirmation (quick reply, 3 buttons)
    "codeverity_location_confirm": {
        "twilio/quick-reply": {
            "body": "📍 Detected address: {{1}}. Is this correct?",
            "actions": [
                {"id": "confirm_address", "title": "✅ Confirm Address"},
                {"id": "edit_address", "title": "✏️ Edit Address"},
                {"id": "resend_gps", "title": "📍 Resend GPS"},
            ],
        }
    },
    # State 3 — photo QA (quick reply, 3 buttons)
    "codeverity_photo_qa": {
        "twilio/quick-reply": {
            "body": "{{1}}",  # e.g. "Photo #3 blurry due to glare. Tap to retake."
            "actions": [
                {"id": "retake_photo", "title": "📷 Retake Photo"},
                {"id": "add_more_photos", "title": "➕ Add More Photos"},
                {"id": "skip_to_voice", "title": "➡️ Skip to Voice"},
            ],
        }
    },
    # State 4 — voice note confirmation (quick reply, 3 buttons)
    "codeverity_voice_confirm": {
        "twilio/quick-reply": {
            "body": "Scope captured. Ready to submit this package?",
            "actions": [
                {"id": "submit_package", "title": "✅ Submit Package"},
                {"id": "rerecord_voice", "title": "🎙️ Re-record Voice"},
                {"id": "add_note", "title": "✏️ Add Note"},
            ],
        }
    },
}


def validate_templates() -> list[str]:
    """Enforce the de-risk constraints. Returns a list of problems (empty == valid)."""
    problems: list[str] = []
    for name, types in TEMPLATES.items():
        if "twilio/quick-reply" in types:
            n = len(types["twilio/quick-reply"]["actions"])
            if n > 3:
                problems.append(
                    f"{name}: {n} quick-reply buttons — max 3 for unapproved in-session sends"
                )
        if "twilio/list-picker" in types:
            n = len(types["twilio/list-picker"]["items"])
            if n > 10:
                problems.append(f"{name}: {n} list items — WhatsApp max is 10")
    return problems


def build_create_payload(name: str) -> dict:
    """Build the JSON body for POST https://content.twilio.com/v1/Content."""
    types = TEMPLATES[name]
    # A text fallback keeps the template usable on channels without rich content.
    if "text" not in types:
        first = next(iter(types.values()))
        types = {**types, "twilio/text": {"body": first.get("body", name)}}
    return {"friendly_name": name, "language": "en", "types": types}


def create_all() -> dict[str, str]:
    """Create every template in the connected Twilio account; return name -> ContentSid."""
    import httpx  # local import so offline tests never need it

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    created: dict[str, str] = {}
    with httpx.Client(auth=(sid, token), timeout=30) as client:
        for name in TEMPLATES:
            resp = client.post(
                "https://content.twilio.com/v1/Content",
                json=build_create_payload(name),
            )
            resp.raise_for_status()
            content_sid = resp.json()["sid"]
            created[name] = content_sid
            print(f"  {name:32s} -> {content_sid}")
    return created


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="CodeVerity Content templates")
    parser.add_argument("--create", action="store_true", help="create templates in Twilio")
    args = parser.parse_args()

    problems = validate_templates()
    if problems:
        print("TEMPLATE VALIDATION FAILED:")
        for p in problems:
            print("  -", p)
        raise SystemExit(1)
    print(f"All {len(TEMPLATES)} templates valid (button/item limits OK).")

    if args.create:
        from dotenv import load_dotenv

        load_dotenv()
        print("Creating templates via Content API...")
        created = create_all()
        print("\nAdd these to your .env:")
        env_map = {
            "codeverity_company_list": "CONTENT_SID_COMPANY_LIST",
            "codeverity_jobsite_list": "CONTENT_SID_JOBSITE_LIST",
            "codeverity_location_confirm": "CONTENT_SID_LOCATION_CONFIRM",
            "codeverity_photo_qa": "CONTENT_SID_PHOTO_QA",
            "codeverity_voice_confirm": "CONTENT_SID_VOICE_CONFIRM",
        }
        for name, env_key in env_map.items():
            print(f'{env_key}="{created.get(name, "")}"')
    else:
        print("Definitions only. Re-run with --create to create them in Twilio.")
        print(json.dumps({n: build_create_payload(n) for n in TEMPLATES}, indent=2))
