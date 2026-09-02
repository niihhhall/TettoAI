"""Phase 3 offline tests for the real integrations.

No network. Validates: Mapbox v6 parsing (dual-layer city/county), Deepgram transcript
parsing, Fireworks extraction schema (mocked LLM), R2 URL/key building, and the §3.2
redirect auth-stripping fix (mock transport).
"""

from __future__ import annotations

import asyncio

import httpx

from app.config import Settings
from app.services.code_extractor import FireworksExtractor, LineItem, SupplementExtraction
from app.services.geocoding import parse_v6_reverse
from app.services.media_storage import R2MediaStorage
from app.services.speech import parse_transcript


def run(coro):
    return asyncio.run(coro)


def _settings(**over) -> Settings:
    base = dict(
        DATABASE_URL="postgresql://u:p@localhost/db?sslmode=disable",
        TWILIO_ACCOUNT_SID="ACtest", TWILIO_AUTH_TOKEN="tok",
        R2_ENDPOINT_URL="https://acct.r2.cloudflarestorage.com",
        R2_ACCESS_KEY_ID="k", R2_SECRET_ACCESS_KEY="s", R2_BUCKET_NAME="codeverity-media",
    )
    base.update(over)
    return Settings(**base)  # type: ignore[arg-type]


# --- Mapbox v6 dual-layer parsing (§3.5) ----------------------------------------

MAPBOX_SAMPLE = {
    "features": [{
        "properties": {
            "full_address": "1420 Elmwood Dr, Dallas, Texas 75201, United States",
            "context": {
                "address": {"name": "1420 Elmwood Dr"},
                "postcode": {"name": "75201"},
                "place": {"name": "Dallas"},
                "district": {"name": "Dallas County"},
                "region": {"name": "Texas", "region_code": "TX"},
            },
        }
    }]
}


def test_mapbox_extracts_city_and_county():
    out = parse_v6_reverse(MAPBOX_SAMPLE)
    assert out["city"] == "Dallas"
    assert out["county"] == "Dallas County"   # the dual-layer field that prevents bad citations
    assert out["state"] == "TX"
    assert out["zip_code"] == "75201"


def test_mapbox_empty_features():
    assert parse_v6_reverse({"features": []}) == {}


# --- Deepgram transcript parsing ------------------------------------------------

def test_deepgram_parse_transcript():
    payload = {"results": {"channels": [{"alternatives": [{"transcript": "missing drip edge"}]}]}}
    assert parse_transcript(payload) == "missing drip edge"


def test_deepgram_parse_transcript_malformed():
    assert parse_transcript({"results": {}}) == ""


# --- Fireworks extraction schema (mocked LLM) -----------------------------------

def test_line_item_schema():
    li = LineItem(code="RFG DRIP", description="Drip edge", qty=180, unit="LF")
    assert li.qty == 180.0


def test_fireworks_extract_maps_to_dicts():
    extractor = FireworksExtractor(api_key="test")  # no network at construction

    class FakeCompletions:
        async def create(self, **kwargs):
            assert kwargs["response_model"] is SupplementExtraction
            assert kwargs["max_retries"] == 1  # single-retry fallback wired
            return SupplementExtraction(
                line_items=[LineItem(code="RFG IWS", description="Ice & Water Shield", qty=2, unit="SQ")],
                summary="ice and water shield required",
            )

    class FakeChat:
        completions = FakeCompletions()

    class FakeClient:
        chat = FakeChat()

    extractor.client = FakeClient()  # type: ignore[assignment]
    items = run(extractor.extract("we need ice and water shield"))
    assert items == [{"code": "RFG IWS", "description": "Ice & Water Shield", "qty": 2.0, "unit": "SQ"}]


# --- R2 URL / key building ------------------------------------------------------

def test_r2_public_url_prefers_custom_domain():
    st = _settings(R2_PUBLIC_CUSTOM_DOMAIN="cdn.codeverity.ai")
    store = R2MediaStorage(st, httpx.AsyncClient())
    assert store._public_url("photos/x.jpg") == "https://cdn.codeverity.ai/photos/x.jpg"


def test_r2_public_url_endpoint_fallback():
    st = _settings(R2_PUBLIC_CUSTOM_DOMAIN=None)
    store = R2MediaStorage(st, httpx.AsyncClient())
    url = store._public_url("photos/x.jpg")
    assert url == "https://acct.r2.cloudflarestorage.com/codeverity-media/photos/x.jpg"


def test_r2_key_prefixes_by_type():
    st = _settings()
    store = R2MediaStorage(st, httpx.AsyncClient())
    assert store._key_for("image/jpeg").startswith("photos/")
    assert store._key_for("audio/ogg").startswith("audio/")


# --- §3.2 fix: drop auth header when following the Twilio -> S3 redirect ---------

def test_twilio_media_download_strips_auth_on_redirect():
    seen: list[tuple[str, str | None]] = []
    twilio_url = "https://api.twilio.com/2010-04-01/Accounts/AC/Messages/MM/Media/ME"
    s3_url = "https://s3.amazonaws.com/twilio-media/ME?sig=abc"

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers.get("authorization")))
        if str(request.url) == twilio_url:
            return httpx.Response(302, headers={"location": s3_url})
        return httpx.Response(200, content=b"\xff\xd8image", headers={"content-type": "image/jpeg"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    store = R2MediaStorage(_settings(), client)

    data, ct = run(store.download_twilio_media(twilio_url, "image/jpeg"))
    run(client.aclose())

    assert data == b"\xff\xd8image"
    assert ct == "image/jpeg"
    # First (Twilio) request carried auth; the redirected S3 request must NOT.
    assert seen[0][0] == twilio_url and seen[0][1] is not None
    assert seen[1][0] == s3_url and seen[1][1] is None
