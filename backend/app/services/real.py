"""RealServices — production implementation of the Services protocol.

Composes R2 media storage, Deepgram STT, Fireworks extraction, and Mapbox geocoding over a
single shared httpx.AsyncClient. Drop-in replacement for StubServices; the state machine is
unchanged. main.py selects this when the required credentials are present.
"""

from __future__ import annotations

import httpx

from app.config import Settings
from app.services import speech
from app.services import geocoding
from app.services.code_extractor import FireworksExtractor
from app.services.media_storage import R2MediaStorage


class RealServices:
    def __init__(self, settings: Settings) -> None:
        self.s = settings
        # Default follow_redirects True (Mapbox/Modal/CRM); Twilio download overrides per-call.
        self._http = httpx.AsyncClient(timeout=60, follow_redirects=True)
        self.media = R2MediaStorage(settings, self._http)
        self.extractor = FireworksExtractor(settings.FIREWORKS_API_KEY or "", settings.FIREWORKS_MODEL)
        self._vision = None  # lazy: only built if a photo is actually captioned

    async def _download_media(self, ref: str, content_type: str) -> tuple[bytes, str]:
        """Provider-aware media fetch: a Meta media ID (Graph API) or a Twilio media URL."""
        if self.s.use_meta:
            return await self.media.download_meta_media(ref, content_type)
        return await self.media.download_twilio_media(ref, content_type)

    async def store_media(self, media_ref: str, content_type: str) -> str:
        data, ct = await self._download_media(media_ref, content_type)
        key = self.media._key_for(ct)
        return await self.media.upload_bytes(data, key, ct)

    async def transcribe(self, audio_url: str) -> str:
        return await speech.transcribe(self._http, self.s.DEEPGRAM_API_KEY or "", audio_url)

    async def extract_line_items(self, transcript: str) -> list[dict]:
        return await self.extractor.extract(transcript)

    async def reverse_geocode(self, lat: float, lon: float) -> dict:
        # Mapbox when a token is configured; otherwise the free OpenStreetMap geocoder.
        if self.s.MAPBOX_ACCESS_TOKEN:
            return await geocoding.reverse_geocode(self._http, self.s.MAPBOX_ACCESS_TOKEN, lat, lon)
        return await geocoding.reverse_geocode_free(self._http, lat, lon)

    async def compile_pdf(self, payload: dict) -> str:
        # Fallback: if Modal isn't configured, render the PDF locally and store it in R2 so a
        # submitted package still completes end-to-end. Modal takes over once MODAL_API_URL is set.
        if not self.s.MODAL_API_URL:
            from uuid import uuid4

            from app.services.pdf import build_supplement_pdf

            pdf_bytes = build_supplement_pdf(payload)
            claim = str(payload.get("claim_number", "UNKNOWN")).replace("/", "-").replace(" ", "_")
            key = f"pdf/{claim}-{uuid4().hex[:8]}.pdf"
            return await self.media.upload_bytes(pdf_bytes, key, "application/pdf")

        resp = await self._http.post(self.s.MODAL_API_URL, json=payload, timeout=90)
        resp.raise_for_status()
        try:
            return resp.json().get("pdf_url", "")
        except Exception:
            return resp.text.strip()

    async def ingest_photo(self, twilio_url: str, content_type: str, seen_hashes: list[int]) -> dict:
        """Download the Twilio photo, run CV quality-control, and store it in R2 if it passes."""
        from app.services import photo_qa

        data, ct = await self._download_media(twilio_url, content_type)
        qc = photo_qa.assess(
            data, seen_hashes,
            blur_min=self.s.PHOTO_BLUR_MIN, dark_max=self.s.PHOTO_DARK_MAX,
            bright_min=self.s.PHOTO_BRIGHT_MIN, dup_hamming=self.s.PHOTO_DUP_HAMMING,
        )
        if not qc.ok:
            return {"ok": False, "url": None, "dhash": qc.dhash, "reasons": qc.reasons}
        key = self.media._key_for(ct)
        url = await self.media.upload_bytes(data, key, ct)
        return {"ok": True, "url": url, "dhash": qc.dhash, "reasons": qc.reasons}

    async def caption_photo(self, image_url: str) -> dict:
        """Semantic vision caption for one photo (decision-support, operator confirms).

        Resilient by design: a vision failure must never break field intake, so any error
        returns {} and the flow falls back to a neutral 'photo saved' acknowledgement.
        """
        if not self.s.FIREWORKS_API_KEY:
            return {}
        try:
            if self._vision is None:
                from app.services.vision import RoofVision
                self._vision = RoofVision(self.s.FIREWORKS_API_KEY, self.s.VISION_MODEL)
            assessment = await self._vision.assess_photo(image_url)
            return assessment.model_dump()
        except Exception:
            return {}

    async def dispatch_crm(self, crm_webhook_url: str | None, payload: dict) -> str:
        """POST the supplement package to the company CRM webhook. Returns a delivery status.

        A non-2xx or transport error is reported as "failed" (not swallowed as success) so
        the operator sees the true outcome and can retry.
        """
        if not crm_webhook_url:
            return "skipped"
        try:
            resp = await self._http.post(crm_webhook_url, json=payload, timeout=30)
            resp.raise_for_status()
            return "delivered"
        except httpx.HTTPError:
            return "failed"

    async def aclose(self) -> None:
        await self._http.aclose()


def has_real_credentials(settings: Settings) -> bool:
    """RealServices needs R2 + Deepgram + Fireworks to be meaningfully functional."""
    return bool(
        settings.R2_ACCESS_KEY_ID
        and settings.R2_SECRET_ACCESS_KEY
        and settings.DEEPGRAM_API_KEY
        and settings.FIREWORKS_API_KEY
    )
