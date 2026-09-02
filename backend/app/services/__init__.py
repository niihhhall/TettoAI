"""External service interfaces.

Phase 2 ships deterministic stubs so the full state machine runs and is testable without
Twilio/R2/Deepgram/Fireworks/Modal. Phase 3/4 provide the real implementations behind the
same `Services` protocol — the state machine never changes.
"""

from __future__ import annotations

from typing import Protocol


class Services(Protocol):
    async def store_media(self, twilio_url: str, content_type: str) -> str: ...
    async def transcribe(self, audio_url: str) -> str: ...
    async def extract_line_items(self, transcript: str) -> list[dict]: ...
    async def reverse_geocode(self, lat: float, lon: float) -> dict: ...
    async def compile_pdf(self, payload: dict) -> str: ...
    # Returns a delivery status: "delivered" | "failed" | "skipped".
    async def dispatch_crm(self, crm_webhook_url: str | None, payload: dict) -> str: ...
    # Download + QA + store one photo. Returns {ok, url, dhash, reasons}.
    async def ingest_photo(self, twilio_url: str, content_type: str, seen_hashes: list[int]) -> dict: ...
    # Semantic vision caption for one already-stored photo. Returns a dict with at least
    # {caption, damage_types[], supports_codes[], quality, claim_relevance}; {} on failure.
    async def caption_photo(self, image_url: str) -> dict: ...


class StubServices:
    """Deterministic no-network implementations used until Phase 3/4 wire real ones."""

    async def store_media(self, twilio_url: str, content_type: str) -> str:
        return f"https://cdn.codeverity.ai/stub/{abs(hash(twilio_url)) % 100000}"

    async def transcribe(self, audio_url: str) -> str:
        return ("Missing drip edge on all eaves, two squares of decking rot on the north "
                "slope, and ice-and-water shield required per code.")

    async def extract_line_items(self, transcript: str) -> list[dict]:
        return [
            {"code": "RFG DRIP", "description": "Drip edge", "qty": 180, "unit": "LF"},
            {"code": "RFG SHTHN", "description": 'OSB Sheathing 1/2"', "qty": 64, "unit": "SF"},
            {"code": "RFG IWS", "description": "Ice & Water Shield", "qty": 2, "unit": "SQ"},
        ]

    async def reverse_geocode(self, lat: float, lon: float) -> dict:
        return {"address": "1420 Elmwood Dr, Dallas, TX 75201", "city": "Dallas",
                "county": "Dallas County", "state": "TX", "zip_code": "75201"}

    async def compile_pdf(self, payload: dict) -> str:
        claim = payload.get("claim_number", "UNKNOWN")
        return f"https://cdn.codeverity.ai/pdf/{claim}.pdf"

    async def dispatch_crm(self, crm_webhook_url: str | None, payload: dict) -> str:
        return "skipped"  # no CRM configured in stub/offline mode

    async def ingest_photo(self, twilio_url: str, content_type: str, seen_hashes: list[int]) -> dict:
        h = abs(hash(twilio_url)) % (10 ** 12)  # deterministic per-URL fingerprint
        if any(h == s for s in seen_hashes):
            return {"ok": False, "url": None, "dhash": h, "reasons": ["duplicate"]}
        return {"ok": True, "url": f"https://cdn.codeverity.ai/stub/{h % 100000}.jpg",
                "dhash": h, "reasons": []}

    async def caption_photo(self, image_url: str) -> dict:
        return {
            "caption": "Roof slope with visible shingle damage and exposed decking",
            "damage_types": ["missing shingles", "exposed decking"],
            "supports_codes": ["RFG DRIP"],
            "quality": "good",
            "claim_relevance": 8,
            "is_roof": True,
            "shows_damage": True,
        }
