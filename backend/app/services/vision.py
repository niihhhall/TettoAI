"""Roof-damage photo assessment via a Fireworks vision model.

Two-layer design (see photo_qa.py for layer 1):
  Layer 1 (CV, photo_qa): cheap mechanical gate — drop blurry / dark / duplicate frames.
  Layer 2 (this module):   semantic understanding — does the photo show roof storm damage,
                           what kind, how relevant to the claim, and which is the BEST
                           evidence photo. This needs a VISION model; text/CV cannot do it.

Output is decision-SUPPORT, not autonomy: the office operator still confirms. Accuracy on
real roof damage must be validated against a labeled field-photo eval set before trusting
it unattended — a vision model can be confidently wrong.
"""

from __future__ import annotations

import instructor
from openai import AsyncOpenAI
from pydantic import BaseModel, Field

FIREWORKS_BASE_URL = "https://api.fireworks.ai/inference/v1"
DEFAULT_VISION_MODEL = "accounts/fireworks/models/glm-5p3-flash"

SYSTEM_PROMPT = (
    "You are a storm-restoration roof inspector reviewing a field photo for an insurance "
    "supplement claim. Judge only what is visible. Identify whether it shows a roof and "
    "whether it evidences storm damage (e.g. missing/lifted shingles, hail bruising, "
    "exposed decking, damaged drip edge, granule loss). Be conservative: do not claim "
    "damage you cannot see. Rate how useful this photo is as claim evidence 0-10."
)


class PhotoAssessment(BaseModel):
    is_roof: bool = Field(description="True if the image shows a roof or roof component")
    shows_damage: bool = Field(description="True if visible storm/roof damage is present")
    damage_types: list[str] = Field(default_factory=list, description="Visible damage categories")
    quality: str = Field(description="Evidence quality: good | fair | poor")
    claim_relevance: int = Field(description="Usefulness as claim evidence, 0-10")
    supports_codes: list[str] = Field(
        default_factory=list, description="Xactimate codes this photo helps justify, if any"
    )
    caption: str = Field(description="One-line description of what the photo shows")


class RoofVision:
    def __init__(self, api_key: str, model: str | None = None) -> None:
        self.model = model or DEFAULT_VISION_MODEL
        self.client = instructor.from_openai(
            AsyncOpenAI(base_url=FIREWORKS_BASE_URL, api_key=api_key),
            mode=instructor.Mode.TOOLS,
        )

    async def assess_photo(self, image_url: str, context: str = "") -> PhotoAssessment:
        user_text = "Assess this roof claim photo."
        if context:
            user_text += f" Field notes for context: {context}"
        return await self.client.chat.completions.create(
            model=self.model,
            response_model=PhotoAssessment,
            max_retries=1,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": user_text},
                        {"type": "image_url", "image_url": {"url": image_url}},
                    ],
                },
            ],
        )

    async def select_best(self, image_urls: list[str], context: str = "") -> dict:
        """Assess each photo and rank by claim relevance. Caller should pass photos that
        already passed the CV quality gate. Returns the best index + all assessments."""
        assessments = [await self.assess_photo(u, context) for u in image_urls]
        best_index = max(
            range(len(assessments)),
            key=lambda i: assessments[i].claim_relevance,
            default=-1,
        )
        return {
            "best_index": best_index,
            "best_url": image_urls[best_index] if best_index >= 0 else None,
            "assessments": [a.model_dump() for a in assessments],
        }
