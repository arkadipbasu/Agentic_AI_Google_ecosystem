"""
Calendar Agent – manages Google Calendar events via Gemini function calling.

The agent wraps the calendar_tool functions as Gemini function declarations
and orchestrates multi-turn conversations for calendar management tasks.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from config.settings import settings
from tools.calendar_tool import (
    create_calendar_event,
    delete_calendar_event,
    get_calendar_event,
    list_calendar_events,
    update_calendar_event,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "calendar_agent"

SYSTEM_PROMPT = """\
You are a helpful calendar assistant that manages Google Calendar events.
You can list, create, update, delete, and retrieve calendar events.
When a user asks about their schedule, always fetch the relevant events first.
Format dates clearly for the user and confirm any changes before applying them.
"""

# ---------------------------------------------------------------------------
# Gemini function declarations for calendar tools
# ---------------------------------------------------------------------------

_LIST_EVENTS = FunctionDeclaration(
    name="list_calendar_events",
    description="List upcoming Google Calendar events.",
    parameters={
        "type": "object",
        "properties": {
            "max_results": {"type": "integer", "description": "Max events to return (default 10)"},
            "time_min": {"type": "string", "description": "RFC3339 lower time bound"},
            "time_max": {"type": "string", "description": "RFC3339 upper time bound"},
            "calendar_id": {"type": "string", "description": "Calendar ID (default: primary)"},
        },
    },
)

_CREATE_EVENT = FunctionDeclaration(
    name="create_calendar_event",
    description="Create a new Google Calendar event.",
    parameters={
        "type": "object",
        "required": ["title", "start_time", "end_time"],
        "properties": {
            "title": {"type": "string"},
            "start_time": {"type": "string", "description": "RFC3339 start time"},
            "end_time": {"type": "string", "description": "RFC3339 end time"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "attendees": {"type": "array", "items": {"type": "string"}},
            "calendar_id": {"type": "string"},
        },
    },
)

_UPDATE_EVENT = FunctionDeclaration(
    name="update_calendar_event",
    description="Update an existing Google Calendar event.",
    parameters={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "event_id": {"type": "string"},
            "title": {"type": "string"},
            "start_time": {"type": "string"},
            "end_time": {"type": "string"},
            "description": {"type": "string"},
            "location": {"type": "string"},
            "calendar_id": {"type": "string"},
        },
    },
)

_DELETE_EVENT = FunctionDeclaration(
    name="delete_calendar_event",
    description="Delete a Google Calendar event by its ID.",
    parameters={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "event_id": {"type": "string"},
            "calendar_id": {"type": "string"},
        },
    },
)

_GET_EVENT = FunctionDeclaration(
    name="get_calendar_event",
    description="Get details of a specific Google Calendar event by ID.",
    parameters={
        "type": "object",
        "required": ["event_id"],
        "properties": {
            "event_id": {"type": "string"},
            "calendar_id": {"type": "string"},
        },
    },
)

CALENDAR_TOOLS = Tool(
    function_declarations=[
        _LIST_EVENTS,
        _CREATE_EVENT,
        _UPDATE_EVENT,
        _DELETE_EVENT,
        _GET_EVENT,
    ]
)

_TOOL_FN_MAP = {
    "list_calendar_events": list_calendar_events,
    "create_calendar_event": create_calendar_event,
    "update_calendar_event": update_calendar_event,
    "delete_calendar_event": delete_calendar_event,
    "get_calendar_event": get_calendar_event,
}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class CalendarAgent:
    """Gemini-powered calendar management agent."""

    def __init__(self) -> None:
        if settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            tools=[CALENDAR_TOOLS],
        )
        self._chat = self._model.start_chat(enable_automatic_function_calling=False)

    def chat(self, user_message: str) -> str:
        """
        Process a user message and return the agent's response.

        Handles function-calling rounds automatically.
        """
        response = self._chat.send_message(user_message)
        return self._process_response(response)

    def _process_response(self, response) -> str:
        """Iteratively resolve function calls until a text response is returned."""
        max_iterations = 5
        for _ in range(max_iterations):
            # Collect any function call parts
            fn_calls = [
                part.function_call
                for candidate in response.candidates
                for part in candidate.content.parts
                if part.function_call.name
            ]
            if not fn_calls:
                # Return the first text part found
                for candidate in response.candidates:
                    for part in candidate.content.parts:
                        if hasattr(part, "text") and part.text:
                            return part.text
                return "I've completed the requested calendar operation."

            # Execute each function call and send results back
            fn_responses = []
            for fn_call in fn_calls:
                fn_name = fn_call.name
                fn_args = dict(fn_call.args)
                logger.debug("CalendarAgent calling %s(%s)", fn_name, fn_args)
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
