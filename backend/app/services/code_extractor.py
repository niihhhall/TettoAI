"""Xactimate line-item extraction via Fireworks.ai Llama-3.3-70B (PRD §3.4).

Fireworks exposes an OpenAI-compatible API. `instructor` wraps the client to force
responses into the Pydantic schema; `max_retries=1` gives the single-retry fallback so a
malformed generation never bubbles up as a 500.
"""

from __future__ import annotations

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_MODEL = "accounts/fireworks/models/gpt-oss-120b"

SYSTEM_PROMPT = (
    "You are a senior storm-restoration estimator preparing a roofing insurance supplement. "
    "You are given the foreman's spoken field notes together with structured observations "
    "from the inspection photos (visible damage types and candidate Xactimate codes). "
    "Produce the roofing supplement line items justified by the described OR pictured damage, "
    "using standard Xactimate codes (e.g. RFG DRIP, RFG SHTHN, RFG IWS, RFG 240, R&R). "
    "When a quantity was not explicitly stated, provide a reasonable industry-standard "
    "estimate and note in the description that it is an estimate for the operator to verify. "
    "Only include items supported by the evidence; do not fabricate damage that is neither "
    "described nor pictured."
)


class LineItem(BaseModel):
    code: str = Field(description="Xactimate code, e.g. 'RFG DRIP'")
    description: str = Field(description="Human-readable line item description")
    qty: float = Field(description="Quantity as a number")
    unit: str = Field(description="Unit of measure: LF, SF, SQ, or EA")


class SupplementExtraction(BaseModel):
    line_items: list[LineItem]
    summary: str = Field(description="One-sentence scope summary")


class FireworksExtractor:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.model = model or DEFAULT_MODEL
        # Function-calling (tools) mode is more reliable than raw JSON for structured
        # extraction on Fireworks function-calling models (e.g. gpt-oss-120b).
        self.client = instructor.from_openai(
            AsyncOpenAI(base_url=FIREWORKS_BASE_URL, api_key=api_key),
            mode=instructor.Mode.TOOLS,
        )

    async def extract(self, transcript: str) -> list[dict]:
        result: SupplementExtraction = await self.client.chat.completions.create(
            model=self.model,
            response_model=SupplementExtraction,
            max_retries=1,  # single-retry fallback (§3.4)
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": transcript},
            ],
        )
        return [li.model_dump() for li in result.line_items]
