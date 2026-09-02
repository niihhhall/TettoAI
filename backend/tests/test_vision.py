"""Offline test for the vision selection logic (model call is mocked, so no network/key).

Proves select_best picks the highest claim-relevance photo. Real model accuracy is
validated separately against a labeled field-photo eval set (not in the unit suite)."""

from __future__ import annotations

import asyncio

from app.services.vision import PhotoAssessment, RoofVision


def run(coro):
    return asyncio.run(coro)


def test_select_best_ranks_by_claim_relevance(monkeypatch):
    v = RoofVision(api_key="test-key")
    canned = {
        "u1": PhotoAssessment(is_roof=True, shows_damage=False, quality="fair",
                              claim_relevance=3, caption="roof edge, no clear damage"),
        "u2": PhotoAssessment(is_roof=True, shows_damage=True, quality="good",
                              claim_relevance=9, caption="missing shingles, exposed decking"),
        "u3": PhotoAssessment(is_roof=False, shows_damage=False, quality="poor",
                              claim_relevance=0, caption="sky"),
    }

    async def fake_assess(url, context=""):
        return canned[url]

    monkeypatch.setattr(v, "assess_photo", fake_assess)

    res = run(v.select_best(["u1", "u2", "u3"], context="hail damage"))
    assert res["best_index"] == 1
    assert res["best_url"] == "u2"
    assert len(res["assessments"]) == 3


def test_select_best_empty():
    v = RoofVision(api_key="test-key")
    res = run(v.select_best([], context=""))
    assert res["best_index"] == -1 and res["best_url"] is None
