"""
MCP tool for Google Maps.

Uses the Google Maps Platform APIs via the `googlemaps` Python client.

Exposes the following tools:
  - geocode_address       – convert an address to coordinates
  - reverse_geocode       – convert coordinates to address
  - search_places         – text search for places
  - get_place_details     – detailed info about a place
  - get_directions        – get directions between two locations
  - get_distance_matrix   – distance/duration matrix for multiple origins/destinations
"""

from __future__ import annotations

import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


def _get_maps_client():
    """Return an authenticated Google Maps client."""
    try:
        import googlemaps
    except ImportError as exc:
        raise ImportError(
            "googlemaps package is required for Maps tools. "
            "Install it with: pip install googlemaps"
        ) from exc

    from config.settings import settings

    if not settings.google_maps_api_key:
        raise ValueError(
            "GOOGLE_MAPS_API_KEY is not set. "
            "Add it to your .env file or environment variables."
        )
    return googlemaps.Client(key=settings.google_maps_api_key)


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def geocode_address(address: str) -> dict[str, Any]:
    """
    Convert a human-readable address into geographic coordinates.

    Args:
        address: The address to geocode (e.g. '1600 Amphitheatre Pkwy, Mountain View, CA').

    Returns:
        A dict with 'place_id', 'formatted_address', 'lat', 'lng'.
    """
    try:
        gmaps = _get_maps_client()
        results = gmaps.geocode(address)
        if not results:
            return {"error": "No results found for the given address.", "address": address}

        first = results[0]
        loc = first["geometry"]["location"]
        return {
            "place_id": first.get("place_id"),
            "formatted_address": first.get("formatted_address"),
            "lat": loc["lat"],
            "lng": loc["lng"],
        }
    except Exception as exc:
        logger.error("Error geocoding address: %s", exc)
        return {"error": str(exc)}


def reverse_geocode(lat: float, lng: float) -> dict[str, Any]:
    """
    Convert geographic coordinates into a human-readable address.

    Args:
        lat: Latitude.
        lng: Longitude.

    Returns:
        A dict with 'formatted_address', 'place_id', and address components.
    """
    try:
        gmaps = _get_maps_client()
        results = gmaps.reverse_geocode((lat, lng))
        if not results:
            return {"error": "No results found for the given coordinates."}

        first = results[0]
        return {
            "place_id": first.get("place_id"),
            "formatted_address": first.get("formatted_address"),
            "address_components": first.get("address_components", []),
        }
    except Exception as exc:
        logger.error("Error reverse geocoding: %s", exc)
        return {"error": str(exc)}


def search_places(
    query: str,
    location: str | None = None,
    radius_meters: int = 5000,
) -> dict[str, Any]:
    """
    Text search for places using Google Places API.

    Args:
        query: The search query (e.g. 'coffee shops near downtown').
        location: Optional bias location as 'lat,lng' string.
        radius_meters: Search radius in meters around `location` (default 5000).

    Returns:
        A dict with 'places' list and 'count'.
    """
    try:
        gmaps = _get_maps_client()
        kwargs: dict[str, Any] = {}
        if location:
            lat_str, lng_str = location.split(",")
            kwargs["location"] = (float(lat_str.strip()), float(lng_str.strip()))
            kwargs["radius"] = radius_meters

        results = gmaps.places(query=query, **kwargs)
        places = []
        for place in results.get("results", [])[:10]:
            geometry = place.get("geometry", {}).get("location", {})
            places.append(
                {
                    "place_id": place.get("place_id"),
                    "name": place.get("name"),
                    "address": place.get("formatted_address") or place.get("vicinity"),
                    "lat": geometry.get("lat"),
                    "lng": geometry.get("lng"),
                    "rating": place.get("rating"),
                    "types": place.get("types", []),
                    "open_now": place.get("opening_hours", {}).get("open_now"),
                }
            )
        return {"places": places, "count": len(places), "query": query}
    except Exception as exc:
        logger.error("Error searching places: %s", exc)
        return {"error": str(exc), "places": [], "count": 0}


def get_place_details(place_id: str) -> dict[str, Any]:
    """
    Get detailed information about a specific place.

    Args:
        place_id: The Google Place ID.

    Returns:
        A dict with place details including address, phone, website, hours, and reviews.
    """
    try:
        gmaps = _get_maps_client()
        fields = [
            "name",
            "formatted_address",
            "geometry",
            "rating",
            "formatted_phone_number",
            "website",
            "opening_hours",
            "reviews",
            "types",
            "url",
        ]
        result = gmaps.place(place_id=place_id, fields=fields)
        place = result.get("result", {})
        geometry = place.get("geometry", {}).get("location", {})
        reviews = [
            {
                "author": r.get("author_name"),
                "rating": r.get("rating"),
                "text": r.get("text"),
            }
            for r in place.get("reviews", [])[:3]
        ]
        return {
            "place_id": place_id,
            "name": place.get("name"),
            "address": place.get("formatted_address"),
            "lat": geometry.get("lat"),
            "lng": geometry.get("lng"),
            "phone": place.get("formatted_phone_number"),
            "website": place.get("website"),
            "rating": place.get("rating"),
            "opening_hours": place.get("opening_hours", {}).get("weekday_text", []),
            "open_now": place.get("opening_hours", {}).get("open_now"),
            "types": place.get("types", []),
            "google_maps_url": place.get("url"),
            "reviews": reviews,
        }
    except Exception as exc:
        logger.error("Error getting place details: %s", exc)
        return {"error": str(exc)}


def get_directions(
    origin: str,
    destination: str,
    mode: str = "driving",
    departure_time: str | None = None,
) -> dict[str, Any]:
    """
    Get turn-by-turn directions between two locations.

    Args:
        origin: Starting location (address or 'lat,lng').
        destination: Ending location (address or 'lat,lng').
        mode: Travel mode – 'driving', 'walking', 'bicycling', or 'transit'.
        departure_time: Optional departure time as ISO 8601 string (for transit/traffic).

    Returns:
        A dict with route summary, distance, duration, and steps.
    """
    try:
        import datetime as dt

        gmaps = _get_maps_client()
        kwargs: dict[str, Any] = {"mode": mode}
        if departure_time:
            kwargs["departure_time"] = dt.datetime.fromisoformat(departure_time)

        results = gmaps.directions(origin, destination, **kwargs)
        if not results:
            return {"error": "No directions found.", "origin": origin, "destination": destination}

        route = results[0]
        leg = route["legs"][0]
        steps = [
            {
                "instruction": s.get("html_instructions", ""),
                "distance": s["distance"]["text"],
                "duration": s["duration"]["text"],
            }
            for s in leg.get("steps", [])
        ]
        return {
            "origin": leg["start_address"],
            "destination": leg["end_address"],
            "distance": leg["distance"]["text"],
            "duration": leg["duration"]["text"],
            "mode": mode,
            "steps": steps,
            "summary": route.get("summary", ""),
        }
    except Exception as exc:
        logger.error("Error getting directions: %s", exc)
        return {"error": str(exc)}


def get_distance_matrix(
    origins: list[str],
    destinations: list[str],
    mode: str = "driving",
) -> dict[str, Any]:
    """
    Calculate travel distance and time between multiple origins and destinations.

    Args:
        origins: List of origin addresses or 'lat,lng' strings.
        destinations: List of destination addresses or 'lat,lng' strings.
        mode: Travel mode – 'driving', 'walking', 'bicycling', or 'transit'.

    Returns:
        A dict with a matrix of distance/duration results.
    """
    try:
        gmaps = _get_maps_client()
        result = gmaps.distance_matrix(origins, destinations, mode=mode)
        rows = []
        for i, row in enumerate(result.get("rows", [])):
            elements = []
            for j, elem in enumerate(row.get("elements", [])):
                elements.append(
                    {
                        "origin": result["origin_addresses"][i],
                        "destination": result["destination_addresses"][j],
                        "distance": elem.get("distance", {}).get("text"),
                        "duration": elem.get("duration", {}).get("text"),
                        "status": elem.get("status"),
                    }
                )
            rows.append(elements)
        return {"matrix": rows, "mode": mode}
    except Exception as exc:
        logger.error("Error getting distance matrix: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Server entry-point
# ---------------------------------------------------------------------------

def create_mcp_server():
    """Create and return an MCP server exposing all Maps tools."""
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("google-maps-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="geocode_address",
                description="Convert an address to geographic coordinates.",
                inputSchema={
                    "type": "object",
                    "required": ["address"],
                    "properties": {"address": {"type": "string"}},
                },
            ),
            Tool(
                name="reverse_geocode",
                description="Convert coordinates to a human-readable address.",
                inputSchema={
                    "type": "object",
                    "required": ["lat", "lng"],
                    "properties": {
                        "lat": {"type": "number"},
                        "lng": {"type": "number"},
                    },
                },
            ),
            Tool(
                name="search_places",
                description="Text search for places using Google Places API.",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "location": {"type": "string", "description": "'lat,lng' bias"},
                        "radius_meters": {"type": "integer", "default": 5000},
                    },
                },
            ),
            Tool(
                name="get_place_details",
                description="Get detailed information about a place by its Place ID.",
                inputSchema={
                    "type": "object",
                    "required": ["place_id"],
                    "properties": {"place_id": {"type": "string"}},
                },
            ),
            Tool(
                name="get_directions",
                description="Get directions between two locations.",
                inputSchema={
                    "type": "object",
                    "required": ["origin", "destination"],
                    "properties": {
                        "origin": {"type": "string"},
                        "destination": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": ["driving", "walking", "bicycling", "transit"],
                            "default": "driving",
                        },
                        "departure_time": {"type": "string"},
                    },
                },
            ),
            Tool(
                name="get_distance_matrix",
                description="Calculate travel distance and time between multiple locations.",
                inputSchema={
                    "type": "object",
                    "required": ["origins", "destinations"],
                    "properties": {
                        "origins": {"type": "array", "items": {"type": "string"}},
                        "destinations": {"type": "array", "items": {"type": "string"}},
                        "mode": {
                            "type": "string",
                            "enum": ["driving", "walking", "bicycling", "transit"],
                            "default": "driving",
                        },
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        tool_map = {
            "geocode_address": geocode_address,
            "reverse_geocode": reverse_geocode,
            "search_places": search_places,
            "get_place_details": get_place_details,
            "get_directions": get_directions,
            "get_distance_matrix": get_distance_matrix,
        }
        fn = tool_map.get(name)
        if fn is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = fn(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server
