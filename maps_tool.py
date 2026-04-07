"""
tools/maps_tool.py
MCP-style wrapper around the Google Maps Platform APIs.
Covers geocoding, place search, directions, and distance matrix.
"""

from typing import Any

import googlemaps

from config import get_settings


def _client() -> googlemaps.Client:
    return googlemaps.Client(key=get_settings().GOOGLE_MAPS_API_KEY)


# ── Tools ─────────────────────────────────────────────────────────────────────

def geocode(address: str) -> dict[str, Any]:
    """Convert a free-text address to lat/lng coordinates."""
    results = _client().geocode(address)
    if not results:
        return {"error": "No results found"}
    loc = results[0]["geometry"]["location"]
    return {
        "formatted_address": results[0]["formatted_address"],
        "lat": loc["lat"],
        "lng": loc["lng"],
        "place_id": results[0].get("place_id"),
    }


def search_places(
    query: str,
    location: str | None = None,
    radius_meters: int = 5000,
    place_type: str | None = None,
) -> list[dict[str, Any]]:
    """Search nearby places by keyword and optional type filter."""
    client = _client()
    kwargs: dict[str, Any] = {"query": query}
    if location:
        geo = geocode(location)
        if "lat" in geo:
            kwargs["location"] = (geo["lat"], geo["lng"])
            kwargs["radius"] = radius_meters
    if place_type:
        kwargs["type"] = place_type
    result = client.places(**kwargs)
    return [
        {
            "name": p["name"],
            "address": p.get("formatted_address", p.get("vicinity", "")),
            "rating": p.get("rating"),
            "place_id": p["place_id"],
            "open_now": p.get("opening_hours", {}).get("open_now"),
        }
        for p in result.get("results", [])[:5]
    ]


def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",             # driving | walking | bicycling | transit
    departure_time: str | None = None, # ISO datetime string
) -> dict[str, Any]:
    """Get step-by-step directions between two locations."""
    client = _client()
    kwargs: dict[str, Any] = {"origin": origin, "destination": destination, "mode": mode}
    if departure_time:
        from datetime import datetime
        kwargs["departure_time"] = datetime.fromisoformat(departure_time)
    routes = client.directions(**kwargs)
    if not routes:
        return {"error": "No route found"}
    leg = routes[0]["legs"][0]
    steps = [
        {"instruction": s["html_instructions"], "distance": s["distance"]["text"]}
        for s in leg["steps"]
    ]
    return {
        "origin": leg["start_address"],
        "destination": leg["end_address"],
        "distance": leg["distance"]["text"],
        "duration": leg["duration"]["text"],
        "steps": steps,
    }


def distance_matrix(
    origins: list[str],
    destinations: list[str],
    mode: str = "driving",
) -> dict[str, Any]:
    """Return distances and travel times for origin/destination pairs."""
    result = _client().distance_matrix(origins=origins, destinations=destinations, mode=mode)
    rows = []
    for i, row in enumerate(result["rows"]):
        for j, element in enumerate(row["elements"]):
            if element["status"] == "OK":
                rows.append({
                    "origin": origins[i],
                    "destination": destinations[j],
                    "distance": element["distance"]["text"],
                    "duration": element["duration"]["text"],
                })
    return {"results": rows}


# ── Tool manifest ─────────────────────────────────────────────────────────────
MAPS_TOOLS = [
    {"name": "geocode",          "description": "Geocode an address to lat/lng",              "fn": geocode},
    {"name": "search_places",    "description": "Search nearby places",                       "fn": search_places},
    {"name": "get_directions",   "description": "Get driving/walking/transit directions",      "fn": get_directions},
    {"name": "distance_matrix",  "description": "Calculate distances between multiple points", "fn": distance_matrix},
]
