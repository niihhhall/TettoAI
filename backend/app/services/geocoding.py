"""Mapbox reverse geocoding with dual-layer city/county resolution (PRD §3.5).

Resolves BOTH the incorporated city (`context.place`) and the county
(`context.district`) so downstream code never cites a city ordinance on a property that
actually sits in unincorporated county jurisdiction.
"""

from __future__ import annotations

import httpx

MAPBOX_V6_REVERSE = "https://api.mapbox.com/search/geocode/v6/reverse"
# Free, key-less reverse geocoder (OpenStreetMap). Used when no Mapbox token is configured.
NOMINATIM_REVERSE = "https://nominatim.openstreetmap.org/reverse"


def parse_v6_reverse(payload: dict) -> dict:
    """Extract address + dual-layer city/county from a Mapbox v6 reverse response."""
    features = payload.get("features") or []
    if not features:
        return {}
    props = features[0].get("properties", {})
    ctx = props.get("context", {})

    def name(key: str) -> str | None:
        node = ctx.get(key) or {}
        return node.get("name")

    region = ctx.get("region") or {}
    return {
        "address": props.get("full_address") or props.get("name"),
        "city": name("place"),            # incorporated locality
        "county": name("district"),       # county (unincorporated fallback)
        "state": region.get("region_code") or region.get("name"),
        "zip_code": name("postcode"),
    }


async def reverse_geocode(http: httpx.AsyncClient, token: str, lat: float, lon: float) -> dict:
    resp = await http.get(
        MAPBOX_V6_REVERSE,
        params={"longitude": lon, "latitude": lat, "access_token": token},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_v6_reverse(resp.json())


def parse_nominatim(payload: dict) -> dict:
    """Extract address + dual-layer city/county from an OpenStreetMap Nominatim response."""
    addr = payload.get("address", {}) or {}
    # Widen the locality fallback so rural / non-US addresses still resolve a city label
    # (Nominatim may place the locality under municipality/suburb/county/state_district).
    city = (addr.get("city") or addr.get("town") or addr.get("village") or addr.get("hamlet")
            or addr.get("municipality") or addr.get("suburb") or addr.get("city_district")
            or addr.get("county") or addr.get("state_district"))
    return {
        "address": payload.get("display_name"),
        "city": city,
        "county": addr.get("county") or addr.get("state_district"),
        "state": addr.get("state"),
        "zip_code": addr.get("postcode"),
    }


async def reverse_geocode_free(http: httpx.AsyncClient, lat: float, lon: float) -> dict:
    """Key-less reverse geocode via OpenStreetMap Nominatim (requires a User-Agent)."""
    resp = await http.get(
        NOMINATIM_REVERSE,
        params={"lat": lat, "lon": lon, "format": "jsonv2", "addressdetails": 1},
        headers={"User-Agent": "CodeVerity/1.0 (field-intake)"},
        follow_redirects=True,
    )
    resp.raise_for_status()
    return parse_nominatim(resp.json())
