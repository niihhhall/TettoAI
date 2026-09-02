"""Deepgram Nova-2 speech-to-text (PRD stack).

Uses the documented REST endpoint over httpx for version stability. Trade-vocabulary
keywords bias recognition toward roofing terms the field crews actually say.
"""

from __future__ import annotations

import httpx

DEEPGRAM_URL = "https://api.deepgram.com/v1/listen"

# Roofing / storm-restoration trade vocabulary to boost recognition accuracy.
TRADE_KEYWORDS = [
    "drip edge", "sheathing", "decking", "ice and water shield", "underlayment",
    "ridge vent", "flashing", "eave", "soffit", "fascia", "square", "shingle",
    "Xactimate", "supplement", "hail", "wind", "granule",
]


def parse_transcript(payload: dict) -> str:
    """Pull the best transcript from a Deepgram prerecorded response."""
    try:
        return payload["results"]["channels"][0]["alternatives"][0]["transcript"]
    except (KeyError, IndexError):
        return ""


async def transcribe(http: httpx.AsyncClient, api_key: str, audio_url: str) -> str:
    params = [
        ("model", "nova-2"),
        ("smart_format", "true"),
        ("language", "en"),
        ("punctuate", "true"),
    ]
    params += [("keywords", kw) for kw in TRADE_KEYWORDS]
    resp = await http.post(
        DEEPGRAM_URL,
        params=params,
        headers={"Authorization": f"Token {api_key}", "Content-Type": "application/json"},
        json={"url": audio_url},
        timeout=120,
    )
    resp.raise_for_status()
    return parse_transcript(resp.json())
