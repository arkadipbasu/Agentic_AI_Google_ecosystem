"""
MCP tool for Google Calendar.

Exposes the following tools via the Model Context Protocol:
  - list_calendar_events   – list upcoming events in a time window
  - create_calendar_event  – create a new event
  - update_calendar_event  – update an existing event
  - delete_calendar_event  – delete an event
  - get_calendar_event     – get details of a specific event
"""

from __future__ import annotations

import json
import logging
import os
from datetime import datetime, timezone
from typing import Any

logger = logging.getLogger(__name__)

# Google Calendar API scopes
SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _get_calendar_service():
    """Return an authenticated Google Calendar service."""
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

    return build("calendar", "v3", credentials=creds)


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------


def list_calendar_events(
    max_results: int = 10,
    time_min: str | None = None,
    time_max: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    List upcoming Google Calendar events.

    Args:
        max_results: Maximum number of events to return (default 10).
        time_min: Lower bound (RFC3339 timestamp). Defaults to now.
        time_max: Upper bound (RFC3339 timestamp). Optional.
        calendar_id: Calendar identifier (default "primary").

    Returns:
        A dict with 'events' list and 'count'.
    """
    try:
        service = _get_calendar_service()
        now = datetime.now(timezone.utc).isoformat()
        kwargs: dict[str, Any] = {
            "calendarId": calendar_id,
            "timeMin": time_min or now,
            "maxResults": max_results,
            "singleEvents": True,
            "orderBy": "startTime",
        }
        if time_max:
            kwargs["timeMax"] = time_max

        result = service.events().list(**kwargs).execute()
        events = result.get("items", [])

        simplified = []
        for event in events:
            start = event.get("start", {})
            end = event.get("end", {})
            simplified.append(
                {
                    "id": event.get("id"),
                    "title": event.get("summary", "(No title)"),
                    "description": event.get("description"),
                    "location": event.get("location"),
                    "start": start.get("dateTime") or start.get("date"),
                    "end": end.get("dateTime") or end.get("date"),
                    "attendees": [
                        a.get("email") for a in event.get("attendees", [])
                    ],
                    "html_link": event.get("htmlLink"),
                }
            )
        return {"events": simplified, "count": len(simplified)}
    except Exception as exc:
        logger.error("Error listing calendar events: %s", exc)
        return {"error": str(exc), "events": [], "count": 0}


def create_calendar_event(
    title: str,
    start_time: str,
    end_time: str,
    description: str | None = None,
    location: str | None = None,
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Create a new Google Calendar event.

    Args:
        title: Event title / summary.
        start_time: Start time in RFC3339 format (e.g. '2024-03-15T09:00:00-07:00').
        end_time: End time in RFC3339 format.
        description: Optional event description.
        location: Optional event location.
        attendees: Optional list of attendee email addresses.
        calendar_id: Calendar identifier (default "primary").

    Returns:
        A dict with event details including 'id' and 'html_link'.
    """
    try:
        service = _get_calendar_service()
        event_body: dict[str, Any] = {
            "summary": title,
            "start": {"dateTime": start_time},
            "end": {"dateTime": end_time},
        }
        if description:
            event_body["description"] = description
        if location:
            event_body["location"] = location
        if attendees:
            event_body["attendees"] = [{"email": email} for email in attendees]

        created = (
            service.events()
            .insert(calendarId=calendar_id, body=event_body)
            .execute()
        )
        return {
            "id": created.get("id"),
            "title": created.get("summary"),
            "start": created.get("start", {}).get("dateTime"),
            "end": created.get("end", {}).get("dateTime"),
            "html_link": created.get("htmlLink"),
            "status": "created",
        }
    except Exception as exc:
        logger.error("Error creating calendar event: %s", exc)
        return {"error": str(exc), "status": "failed"}


def update_calendar_event(
    event_id: str,
    title: str | None = None,
    start_time: str | None = None,
    end_time: str | None = None,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Update an existing Google Calendar event.

    Args:
        event_id: The Google Calendar event ID.
        title: New event title (optional).
        start_time: New start time in RFC3339 format (optional).
        end_time: New end time in RFC3339 format (optional).
        description: New description (optional).
        location: New location (optional).
        calendar_id: Calendar identifier (default "primary").

    Returns:
        Updated event details.
    """
    try:
        service = _get_calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()

        if title:
            event["summary"] = title
        if description:
            event["description"] = description
        if location:
            event["location"] = location
        if start_time:
            event["start"] = {"dateTime": start_time}
        if end_time:
            event["end"] = {"dateTime": end_time}

        updated = (
            service.events()
            .update(calendarId=calendar_id, eventId=event_id, body=event)
            .execute()
        )
        return {
            "id": updated.get("id"),
            "title": updated.get("summary"),
            "start": updated.get("start", {}).get("dateTime"),
            "end": updated.get("end", {}).get("dateTime"),
            "html_link": updated.get("htmlLink"),
            "status": "updated",
        }
    except Exception as exc:
        logger.error("Error updating calendar event: %s", exc)
        return {"error": str(exc), "status": "failed"}


def delete_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Delete a Google Calendar event.

    Args:
        event_id: The Google Calendar event ID to delete.
        calendar_id: Calendar identifier (default "primary").

    Returns:
        A dict with 'status' indicating success or failure.
    """
    try:
        service = _get_calendar_service()
        service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
        return {"status": "deleted", "event_id": event_id}
    except Exception as exc:
        logger.error("Error deleting calendar event: %s", exc)
        return {"error": str(exc), "status": "failed"}


def get_calendar_event(
    event_id: str,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """
    Get details of a specific Google Calendar event.

    Args:
        event_id: The Google Calendar event ID.
        calendar_id: Calendar identifier (default "primary").

    Returns:
        Event details as a dict.
    """
    try:
        service = _get_calendar_service()
        event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
        start = event.get("start", {})
        end = event.get("end", {})
        return {
            "id": event.get("id"),
            "title": event.get("summary", "(No title)"),
            "description": event.get("description"),
            "location": event.get("location"),
            "start": start.get("dateTime") or start.get("date"),
            "end": end.get("dateTime") or end.get("date"),
            "attendees": [a.get("email") for a in event.get("attendees", [])],
            "html_link": event.get("htmlLink"),
        }
    except Exception as exc:
        logger.error("Error getting calendar event: %s", exc)
        return {"error": str(exc)}


# ---------------------------------------------------------------------------
# MCP Server entry-point
# ---------------------------------------------------------------------------

def create_mcp_server():
    """Create and return an MCP server exposing all calendar tools."""
    from mcp.server import Server
    from mcp.server.stdio import stdio_server
    from mcp.types import Tool, TextContent

    server = Server("google-calendar-mcp")

    @server.list_tools()
    async def list_tools() -> list[Tool]:
        return [
            Tool(
                name="list_calendar_events",
                description="List upcoming Google Calendar events.",
                inputSchema={
                    "type": "object",
                    "properties": {
                        "max_results": {"type": "integer", "default": 10},
                        "time_min": {"type": "string", "description": "RFC3339 lower bound"},
                        "time_max": {"type": "string", "description": "RFC3339 upper bound"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                },
            ),
            Tool(
                name="create_calendar_event",
                description="Create a new Google Calendar event.",
                inputSchema={
                    "type": "object",
                    "required": ["title", "start_time", "end_time"],
                    "properties": {
                        "title": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                        "attendees": {"type": "array", "items": {"type": "string"}},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                },
            ),
            Tool(
                name="update_calendar_event",
                description="Update an existing Google Calendar event.",
                inputSchema={
                    "type": "object",
                    "required": ["event_id"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "title": {"type": "string"},
                        "start_time": {"type": "string"},
                        "end_time": {"type": "string"},
                        "description": {"type": "string"},
                        "location": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                },
            ),
            Tool(
                name="delete_calendar_event",
                description="Delete a Google Calendar event.",
                inputSchema={
                    "type": "object",
                    "required": ["event_id"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                },
            ),
            Tool(
                name="get_calendar_event",
                description="Get details of a specific Google Calendar event.",
                inputSchema={
                    "type": "object",
                    "required": ["event_id"],
                    "properties": {
                        "event_id": {"type": "string"},
                        "calendar_id": {"type": "string", "default": "primary"},
                    },
                },
            ),
        ]

    @server.call_tool()
    async def call_tool(name: str, arguments: dict) -> list[TextContent]:
        tool_map = {
            "list_calendar_events": list_calendar_events,
            "create_calendar_event": create_calendar_event,
            "update_calendar_event": update_calendar_event,
            "delete_calendar_event": delete_calendar_event,
            "get_calendar_event": get_calendar_event,
        }
        fn = tool_map.get(name)
        if fn is None:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]
        result = fn(**arguments)
        return [TextContent(type="text", text=json.dumps(result, indent=2))]

    return server
