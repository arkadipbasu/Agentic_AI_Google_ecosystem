"""
Maps Agent – answers location and navigation queries via Gemini function calling.
"""

from __future__ import annotations

import json
import logging

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from config.settings import settings
from tools.maps_tool import (
    geocode_address,
    get_directions,
    get_distance_matrix,
    get_place_details,
    reverse_geocode,
    search_places,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "maps_agent"

SYSTEM_PROMPT = """\
You are a helpful location and navigation assistant.
You can search for places, get directions, calculate distances, and look up
detailed information about specific locations.
Always present distances in human-readable format and highlight important
details like travel time, open/closed status, and ratings.
"""

# ---------------------------------------------------------------------------
# Gemini function declarations
# ---------------------------------------------------------------------------

_GEOCODE = FunctionDeclaration(
    name="geocode_address",
    description="Convert a human-readable address into geographic coordinates.",
    parameters={
        "type": "object",
        "required": ["address"],
        "properties": {"address": {"type": "string"}},
    },
)

_REVERSE_GEOCODE = FunctionDeclaration(
    name="reverse_geocode",
    description="Convert geographic coordinates into a human-readable address.",
    parameters={
        "type": "object",
        "required": ["lat", "lng"],
        "properties": {
            "lat": {"type": "number"},
            "lng": {"type": "number"},
        },
    },
)

_SEARCH_PLACES = FunctionDeclaration(
    name="search_places",
    description="Search for places using a text query, optionally near a location.",
    parameters={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "location": {"type": "string", "description": "'lat,lng' bias point"},
            "radius_meters": {"type": "integer", "description": "Search radius in metres"},
        },
    },
)

_GET_PLACE_DETAILS = FunctionDeclaration(
    name="get_place_details",
    description="Get detailed information about a place by its Google Place ID.",
    parameters={
        "type": "object",
        "required": ["place_id"],
        "properties": {"place_id": {"type": "string"}},
    },
)

_GET_DIRECTIONS = FunctionDeclaration(
    name="get_directions",
    description="Get turn-by-turn directions between two locations.",
    parameters={
        "type": "object",
        "required": ["origin", "destination"],
        "properties": {
            "origin": {"type": "string"},
            "destination": {"type": "string"},
            "mode": {
                "type": "string",
                "enum": ["driving", "walking", "bicycling", "transit"],
            },
            "departure_time": {"type": "string"},
        },
    },
)

_DISTANCE_MATRIX = FunctionDeclaration(
    name="get_distance_matrix",
    description="Calculate travel distance and time for multiple origins/destinations.",
    parameters={
        "type": "object",
        "required": ["origins", "destinations"],
        "properties": {
            "origins": {"type": "array", "items": {"type": "string"}},
            "destinations": {"type": "array", "items": {"type": "string"}},
            "mode": {
                "type": "string",
                "enum": ["driving", "walking", "bicycling", "transit"],
            },
        },
    },
)

MAPS_TOOLS = Tool(
    function_declarations=[
        _GEOCODE,
        _REVERSE_GEOCODE,
        _SEARCH_PLACES,
        _GET_PLACE_DETAILS,
        _GET_DIRECTIONS,
        _DISTANCE_MATRIX,
    ]
)

_TOOL_FN_MAP = {
    "geocode_address": geocode_address,
    "reverse_geocode": reverse_geocode,
    "search_places": search_places,
    "get_place_details": get_place_details,
    "get_directions": get_directions,
    "get_distance_matrix": get_distance_matrix,
}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class MapsAgent:
    """Gemini-powered location and navigation agent."""

    def __init__(self) -> None:
        if settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            tools=[MAPS_TOOLS],
        )
        self._chat = self._model.start_chat(enable_automatic_function_calling=False)

    def chat(self, user_message: str) -> str:
        """Process a user message and return the agent's response."""
        response = self._chat.send_message(user_message)
        return self._process_response(response)

    def _process_response(self, response) -> str:
        """Iteratively resolve function calls until a text response is returned."""
        max_iterations = 5
        for _ in range(max_iterations):
            fn_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if part.function_call.name
            ]
            if not fn_calls:
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text
                return "I've completed the requested maps operation."

            fn_responses = []
            for fn_call in fn_calls:
                fn_name = fn_call.name
                fn_args = dict(fn_call.args)
                logger.debug("MapsAgent calling %s(%s)", fn_name, fn_args)
                fn = _TOOL_FN_MAP.get(fn_name)
                result = fn(**fn_args) if fn else {"error": f"Unknown function: {fn_name}"}
                fn_responses.append(
                    genai.protos.Part(
                        function_response=genai.protos.FunctionResponse(
                            name=fn_name,
                            response={"result": json.dumps(result)},
                        )
                    )
                )

            response = self._chat.send_message(fn_responses)

        return "I was unable to complete the request after multiple attempts."
