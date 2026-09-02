"""CodeVerity WhatsApp Content templates + ContentSid resolution.

De-risk constraints enforced:
  * quick-reply: <= 3 actions to remain sendable IN-SESSION without approval.
  * list-picker: cannot initiate a session; <= 10 items.
  * each action/item `id` is returned in the inbound ButtonPayload field -> routing key.
"""

from __future__ import annotations

from app.config import get_settings

# friendly_name -> Content API "types" payload
TEMPLATES: dict[str, dict] = {
    "codeverity_company_list": {
        "twilio/list-picker": {
            "body": "Please select your company to continue.",
            "button": "Select company",
            "items": [
                {"id": "company_apex", "item": "Apex Roofing", "description": "Code 4821"},
                {"id": "company_titan", "item": "Titan Storm Restoration", "description": "Code 7710"},
                {"id": "enter_company_code", "item": "Enter company code", "description": "Type your code manually"},
            ],
        }
    },
    "codeverity_jobsite_list": {
        "twilio/list-picker": {
            "body": "Please select the jobsite you are inspecting.",
            "button": "Select jobsite",
            "items": [
                {"id": "job_1", "item": "{{1}}", "description": "{{2}}"},
                {"id": "new_jobsite", "item": "New jobsite", "description": "Start a new inspection"},
            ],
        }
    },
    "codeverity_location_confirm": {
        "twilio/quick-reply": {
            "body": "We detected this address:\n{{1}}\n\nIs this correct?",
            "actions": [
                {"id": "confirm_address", "title": "Confirm address"},
                {"id": "edit_address", "title": "Edit address"},
                {"id": "resend_gps", "title": "Resend location"},
            ],
        }
    },
    "codeverity_photos_done": {
        "twilio/quick-reply": {
            "body": "You have added {{1}} photo(s). Would you like to add more, or continue to the voice summary?",
            "actions": [
                {"id": "photos_add_more", "title": "Add more photos"},
                {"id": "photos_done", "title": "Continue"},
            ],
        }
    },
    "codeverity_voice_confirm": {
        "twilio/quick-reply": {
            "body": "{{1}}",
            "actions": [
                {"id": "submit_package", "title": "Submit package"},
                {"id": "rerecord_voice", "title": "Re-record voice"},
                {"id": "add_note", "title": "Add note"},
            ],
        }
    },
}

# template friendly_name -> settings attribute holding its ContentSid
_TEMPLATE_ENV = {
    "codeverity_company_list": "CONTENT_SID_COMPANY_LIST",
    "codeverity_jobsite_list": "CONTENT_SID_JOBSITE_LIST",
    "codeverity_location_confirm": "CONTENT_SID_LOCATION_CONFIRM",
    "codeverity_photo_qa": "CONTENT_SID_PHOTO_QA",
    "codeverity_voice_confirm": "CONTENT_SID_VOICE_CONFIRM",
}


def content_sid_for(template_name: str) -> str:
    """Resolve a template name to its ContentSid. Offline, returns a sentinel so callers
    (and tests) can still assert which template would be sent."""
    attr = _TEMPLATE_ENV.get(template_name)
    sid = getattr(get_settings(), attr, None) if attr else None
    return sid or f"OFFLINE:{template_name}"


def validate_templates() -> list[str]:
    problems: list[str] = []
    for name, types in TEMPLATES.items():
        if "twilio/quick-reply" in types and len(types["twilio/quick-reply"]["actions"]) > 3:
            problems.append(f"{name}: >3 quick-reply buttons (in-session unapproved cap)")
        if "twilio/list-picker" in types and len(types["twilio/list-picker"]["items"]) > 10:
            problems.append(f"{name}: >10 list items (WhatsApp cap)")
    return problems
