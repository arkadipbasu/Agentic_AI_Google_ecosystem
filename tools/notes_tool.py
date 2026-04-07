"""
MCP tool for Notes management via Google Tasks API.

Google Tasks serves as the notes/to-do backend because Google Keep
does not have a public REST API. Tasks lists are used to represent
note "categories", and individual tasks carry the note content.

Exposes the following tools:
  - list_notes        – list all notes / tasks
  - create_note       – create a new note
  - update_note       – update an existing note
  - delete_note       – delete a note
  - search_notes      – search notes by keyword
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

logger = logging.getLogger(__name__)

SCOPES = ["https://www.googleapis.com/auth/tasks"]


def _get_tasks_service():
    """Return an authenticated Google Tasks service."""
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    from config.settings import settings

    creds = None
    token_path = settings.google_token_path
    creds_path = settings.google_credentials_path

    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(
                    f"Google credentials file not found at '{creds_path}'. "
                    "Download it from https://console.cloud.google.com/apis/credentials "
                    "and set GOOGLE_CREDENTIALS_PATH in your .env file."
                )
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, "w") as token_file:
            token_file.write(creds.to_json())

    return build("tasks", "v1", credentials=creds)


def _get_or_create_tasklist(service, list_name: str = "Notes") -> str:
    """Return the tasklist ID for `list_name`, creating it if necessary."""
    result = service.tasklists().list().execute()
    for tl in result.get("items", []):
        if tl.get("title") == list_name:
            return tl["id"]
    new_list = service.tasklists().insert(body={"title": list_name}).execute()
    return new_list["id"]


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def list_notes(
    list_name: str = "Notes",
    max_results: int = 20,
    show_completed: bool = False,
) -> dict[str, Any]:
    """
    List notes stored in Google Tasks.

    Args:
        list_name: Name of the task list to use as the notes category (default "Notes").
        max_results: Maximum number of notes to return.
        show_completed: Whether to include completed/deleted notes.

    Returns:
        A dict with 'notes' list and 'count'.
    """
    try:
        service = _get_tasks_service()
        list_id = _get_or_create_tasklist(service, list_name)
        result = service.tasks().list(
            tasklist=list_id,
            maxResults=max_results,
            showCompleted=show_completed,
            showDeleted=False,
            showHidden=show_completed,
        ).execute()

        notes = []
        for task in result.get("items", []):
            notes.append(
                {
                    "id": task.get("id"),
                    "title": task.get("title", "(Untitled)"),
                    "content": task.get("notes"),
                    "due": task.get("due"),
                    "status": task.get("status"),
                    "updated": task.get("updated"),
                }
            )
        return {"notes": notes, "count": len(notes), "list_name": list_name}
    except Exception as exc:
        logger.error("Error listing notes: %s", exc)
        return {"error": str(exc), "notes": [], "count": 0}


def create_note(
    title: str,
    content: str | None = None,
    due_date: str | None = None,
    list_name: str = "Notes",
) -> dict[str, Any]:
    """
    Create a new note (stored as a Google Task).

    Args:
        title: Note title.
        content: Note body / content.
        due_date: Optional due date in RFC3339 format.
        list_name: Name of the task list to store the note in.

    Returns:
        A dict with the created note details.
    """
    try:
        service = _get_tasks_service()
        list_id = _get_or_create_tasklist(service, list_name)
        task_body: dict[str, Any] = {"title": title}
        if content:
            task_body["notes"] = content
        if due_date:
            task_body["due"] = due_date

        created = service.tasks().insert(tasklist=list_id, body=task_body).execute()
        return {
            "id": created.get("id"),
            "title": created.get("title"),
            "content": created.get("notes"),
            "due": created.get("due"),
            "status": "created",
            "list_name": list_name,
        }
    except Exception as exc:
        logger.error("Error creating note: %s", exc)
        return {"error": str(exc), "status": "failed"}


def update_note(
    note_id: str,
    title: str | None = None,
    content: str | None = None,
    due_date: str | None = None,
    mark_complete: bool = False,
    list_name: str = "Notes",
) -> dict[str, Any]:
    """
    Update an existing note.

    Args:
        note_id: Google Tasks task ID.
        title: New title (optional).
        content: New content (optional).
        due_date: New due date in RFC3339 format (optional).
        mark_complete: If True, marks the note as completed.
        list_name: Name of the task list that contains the note.

    Returns:
        Updated note details.
    """
    try:
        service = _get_tasks_service()
        list_id = _get_or_create_tasklist(service, list_name)
        task = service.tasks().get(tasklist=list_id, task=note_id).execute()

        if title:
            task["title"] = title
        if content:
            task["notes"] = content
        if due_date:
            task["due"] = due_date
        if mark_complete:
            task["status"] = "completed"

        updated = service.tasks().update(
            tasklist=list_id, task=note_id, body=task
        ).execute()
        return {
            "id": updated.get("id"),
            "title": updated.get("title"),
            "content": updated.get("notes"),
            "status": "updated",
            "list_name": list_name,
        }
    except Exception as exc:
        logger.error("Error updating note: %s", exc)
        return {"error": str(exc), "status": "failed"}


def delete_note(
    note_id: str,
    list_name: str = "Notes",
) -> dict[str, Any]:
    """
    Delete a note.

    Args:
        note_id: Google Tasks task ID to delete.
        list_name: Name of the task list that contains the note.

    Returns:
        A dict with 'status'.
    """
    try:
        service = _get_tasks_service()
        list_id = _get_or_create_tasklist(service, list_name)
        service.tasks().delete(tasklist=list_id, task=note_id).execute()
        return {"status": "deleted", "note_id": note_id}
    except Exception as exc:
        logger.error("Error deleting note: %s", exc)
        return {"error": str(exc), "status": "failed"}


def search_notes(
    query: str,
    list_name: str = "Notes",
    max_results: int = 20,
) -> dict[str, Any]:
    """
    Search notes by keyword (client-side filtering of Google Tasks).

    Args:
        query: Keyword to search for in note titles and content.
        list_name: Name of the task list to search.
        max_results: Maximum number of matching notes to return.

    Returns:
        A dict with matching 'notes' and 'count'.
    """
    result = list_notes(list_name=list_name, max_results=100, show_completed=False)
    if "error" in result:
        return result

    query_lower = query.lower()
    matches = [
        note
        for note in result["notes"]
        if query_lower in (note.get("title") or "").lower()
        or query_lower in (note.get("content") or "").lower()
    ][:max_results]

    return {"notes": matches, "count": len(matches), "query": query}


# ---------------------------------------------------------------------------
# MCP Server entry-point
# ---------------------------------------------------------------------------

def create_mcp_server():
    """Create and return an MCP server exposing all notes tools."""
    from mcp.server import Server
    from mcp.types import Tool, TextContent

    server = Server("google-notes-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="list_notes",
                description="List notes stored as Google Tasks.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "list_name": {"type": "string", "default": "Notes"},
                        "max_results": {"type": "integer", "default": 20},
                        "show_completed": {"type": "boolean", "default": False},
                    },
                },
            ),
            Tool(
                name="create_note",
                description="Create a new note.",
                inputSchema={
                    "type": "object",
                    "required": ["title"],
                    "properties": {
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "due_date": {"type": "string"},
                        "list_name": {"type": "string", "default": "Notes"},
                    },
                },
            ),
            Tool(
                name="update_note",
                description="Update an existing note.",
                inputSchema={
                    "type": "object",
                    "required": ["note_id"],
                    "properties": {
                        "note_id": {"type": "string"},
                        "title": {"type": "string"},
                        "content": {"type": "string"},
                        "due_date": {"type": "string"},
                        "mark_complete": {"type": "boolean", "default": False},
                        "list_name": {"type": "string", "default": "Notes"},
                    },
                },
            ),
            Tool(
                name="delete_note",
                description="Delete a note.",
                inputSchema={
                    "type": "object",
                    "required": ["note_id"],
                    "properties": {
                        "note_id": {"type": "string"},
                        "list_name": {"type": "string", "default": "Notes"},
                    },
                },
            ),
            Tool(
                name="search_notes",
                description="Search notes by keyword.",
                inputSchema={
                    "type": "object",
                    "required": ["query"],
                    "properties": {
                        "query": {"type": "string"},
                        "list_name": {"type": "string", "default": "Notes"},
                        "max_results": {"type": "integer", "default": 20},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        tool_map = {
            "list_notes": list_notes,
            "create_note": create_note,
            "update_note": update_note,
            "delete_note": delete_note,
            "search_notes": search_notes,
        }
        fn = tool_map.get(name)
        if fn is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = fn(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server
