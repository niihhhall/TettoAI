"""Domain models and message/action types for the state machine.

These are transport-agnostic so the state machine can be unit-tested with no DB and no
Twilio account (mirroring the validated spike).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from uuid import UUID


# --- Persistent domain entities -------------------------------------------------

@dataclass
class Company:
    company_id: UUID
    company_name: str
    invite_code: str
    crm_type: str = "JobNimbus"
    crm_webhook_url: str | None = None


@dataclass
class CrewMember:
    crew_id: UUID
    company_id: UUID | None
    phone_number: str
    full_name: str
    role: str = "Foreman"
    preferred_language: str = "en"
    total_bounties_earned: Decimal = Decimal("0.00")
    last_inbound_at: datetime | None = None


@dataclass
class Operator:
    operator_id: UUID
    company_id: UUID | None
    email: str
    password_hash: str
    role: str = "operator"


@dataclass
class Jobsite:
    job_id: UUID
    company_id: UUID
    property_address: str
    zip_code: str
    city: str
    state: str
    claim_number: str | None = None
    county: str | None = None
    municipal_code_summary: str | None = None


@dataclass
class InspectionSession:
    session_id: UUID
    crew_id: UUID
    job_id: UUID | None = None
    current_state: str = "STATE_1_JOBSITE"
    approved_photos: list[str] = field(default_factory=list)
    # Per-photo evidence records (the linked-evidence model). Each entry:
    #   {url, caption, damage_types[], supports_codes[], quality, claim_relevance,
    #    voice_note_url?, transcript?}
    # approved_photos stays as the flat URL list (count + PDF ordering); photo_evidence
    # carries the semantic layer used to link photos to Xactimate line items.
    photo_evidence: list[dict] = field(default_factory=list)
    voice_note_url: str | None = None
    transcription_text: str | None = None
    structured_line_items: list[dict] = field(default_factory=list)
    pdf_url: str | None = None
    bounty_status: str = "PENDING"
    crm_status: str | None = None
    supplement_value: Decimal | None = None
    created_at: datetime | None = None


# Bounty paid to a foreman per approved package (credited on operator approval).
BOUNTY_AMOUNT = Decimal("25.00")


# --- Conversation state names (inspection_sessions.current_state) ---------------

class State:
    ONBOARD_NAME = "STATE_0_5_NAME"
    ONBOARD_COMPANY = "STATE_0_5_COMPANY"
    JOBSITE = "STATE_1_JOBSITE"
    LOCATION = "STATE_2_LOCATION"
    PHOTOS = "STATE_3_PHOTOS"
    VOICE = "STATE_4_VOICE"
    CONFIRM = "STATE_5_CONFIRM"
    COMPLETE = "STATE_6_COMPLETE"


# --- Inbound / outbound message shapes ------------------------------------------

@dataclass
class InboundMessage:
    from_: str                       # whatsapp:+E164
    body: str = ""
    button_payload: str | None = None  # ButtonPayload / ListId routing key
    profile_name: str | None = None
    num_media: int = 0
    media_urls: list[str] = field(default_factory=list)
    media_content_types: list[str] = field(default_factory=list)
    message_sid: str | None = None
    # WhatsApp location-pin fields (present when the foreman shares their location).
    latitude: float | None = None
    longitude: float | None = None
    location_label: str | None = None


@dataclass
class OutboundAction:
    """What to send next. Exactly one of template / text is set."""
    template: str | None = None
    text: str | None = None
    variables: dict | None = None
