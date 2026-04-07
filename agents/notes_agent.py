"""
Notes Agent – manages notes via Google Tasks using Gemini function calling.
"""

from __future__ import annotations

import json
import logging

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool

from config.settings import settings
from tools.notes_tool import (
    create_note,
    delete_note,
    list_notes,
    search_notes,
    update_note,
)

logger = logging.getLogger(__name__)

AGENT_NAME = "notes_agent"

SYSTEM_PROMPT = """\
You are a helpful notes assistant that manages the user's notes and to-do items.
Notes are stored as Google Tasks. You can list, create, update, delete, and search notes.
When asked to save information, create a well-titled note with the content structured clearly.
When searching, use descriptive keywords that the user might have used.
"""

# ---------------------------------------------------------------------------
# Gemini function declarations
# ---------------------------------------------------------------------------

_LIST_NOTES = FunctionDeclaration(
    name="list_notes",
    description="List notes stored as Google Tasks.",
    parameters={
        "type": "object",
        "properties": {
            "list_name": {"type": "string", "description": "Task list name (default: Notes)"},
            "max_results": {"type": "integer", "description": "Max notes (default: 20)"},
            "show_completed": {"type": "boolean", "description": "Include completed notes"},
        },
    },
)

_CREATE_NOTE = FunctionDeclaration(
    name="create_note",
    description="Create a new note.",
    parameters={
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string"},
            "content": {"type": "string", "description": "Note body"},
            "due_date": {"type": "string", "description": "RFC3339 due date"},
            "list_name": {"type": "string", "description": "Task list (default: Notes)"},
        },
    },
)

_UPDATE_NOTE = FunctionDeclaration(
    name="update_note",
    description="Update an existing note.",
    parameters={
        "type": "object",
        "required": ["note_id"],
        "properties": {
            "note_id": {"type": "string"},
            "title": {"type": "string"},
            "content": {"type": "string"},
            "due_date": {"type": "string"},
            "mark_complete": {"type": "boolean"},
            "list_name": {"type": "string"},
        },
    },
)

_DELETE_NOTE = FunctionDeclaration(
    name="delete_note",
    description="Delete a note by its ID.",
    parameters={
        "type": "object",
        "required": ["note_id"],
        "properties": {
            "note_id": {"type": "string"},
            "list_name": {"type": "string"},
        },
    },
)

_SEARCH_NOTES = FunctionDeclaration(
    name="search_notes",
    description="Search notes by keyword.",
    parameters={
        "type": "object",
        "required": ["query"],
        "properties": {
            "query": {"type": "string"},
            "list_name": {"type": "string"},
            "max_results": {"type": "integer"},
        },
    },
)

NOTES_TOOLS = Tool(
    function_declarations=[
        _LIST_NOTES,
        _CREATE_NOTE,
        _UPDATE_NOTE,
        _DELETE_NOTE,
        _SEARCH_NOTES,
    ]
)

_TOOL_FN_MAP = {
    "list_notes": list_notes,
    "create_note": create_note,
    "update_note": update_note,
    "delete_note": delete_note,
    "search_notes": search_notes,
}


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class NotesAgent:
    """Gemini-powered notes management agent."""

    def __init__(self) -> None:
        if settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            tools=[NOTES_TOOLS],
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
                return "I've completed the requested notes operation."

            fn_responses = []
            for fn_call in fn_calls:
                fn_name = fn_call.name
                fn_args = dict(fn_call.args)
                logger.debug("NotesAgent calling %s(%s)", fn_name, fn_args)
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
