"""
tools/calendar_tool.py
MCP-style wrapper around the Google Calendar API.
Each method maps 1-to-1 with a tool the Calendar Agent can call.
"""

from datetime import datetime, timezone
from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import get_settings

SCOPES = ["https://www.googleapis.com/auth/calendar"]


def _calendar_service():
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_KEY_PATH, scopes=SCOPES
    )
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


# ── Tools ─────────────────────────────────────────────────────────────────────

def list_events(
    calendar_id: str = "primary",
    time_min: str | None = None,
    time_max: str | None = None,
    max_results: int = 10,
) -> list[dict[str, Any]]:
    """Return upcoming calendar events within the given time window."""
    service = _calendar_service()
    now = datetime.now(timezone.utc).isoformat()
    events_result = (
        service.events()
        .list(
            calendarId=calendar_id,
            timeMin=time_min or now,
            timeMax=time_max,
            maxResults=max_results,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    items = events_result.get("items", [])
    return [
        {
            "id": e["id"],
            "summary": e.get("summary", "(no title)"),
            "start": e["start"].get("dateTime", e["start"].get("date")),
            "end": e["end"].get("dateTime", e["end"].get("date")),
            "location": e.get("location"),
            "description": e.get("description"),
        }
        for e in items
    ]


def create_event(
    summary: str,
    start_datetime: str,          # ISO 8601, e.g. "2024-06-01T10:00:00+05:30"
    end_datetime: str,
    description: str = "",
    location: str = "",
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Create a new calendar event and return the created event dict."""
    service = _calendar_service()
    event_body = {
        "summary": summary,
        "description": description,
        "location": location,
        "start": {"dateTime": start_datetime},
        "end": {"dateTime": end_datetime},
    }
    created = service.events().insert(calendarId=calendar_id, body=event_body).execute()
    return {"id": created["id"], "htmlLink": created.get("htmlLink"), "summary": summary}


def update_event(
    event_id: str,
    summary: str | None = None,
    start_datetime: str | None = None,
    end_datetime: str | None = None,
    description: str | None = None,
    location: str | None = None,
    calendar_id: str = "primary",
) -> dict[str, Any]:
    """Patch an existing calendar event."""
    service = _calendar_service()
    event = service.events().get(calendarId=calendar_id, eventId=event_id).execute()
    if summary:
        event["summary"] = summary
    if description is not None:
        event["description"] = description
    if location is not None:
        event["location"] = location
    if start_datetime:
        event["start"] = {"dateTime": start_datetime}
    if end_datetime:
        event["end"] = {"dateTime": end_datetime}
    updated = (
        service.events()
        .update(calendarId=calendar_id, eventId=event_id, body=event)
        .execute()
    )
    return {"id": updated["id"], "updated": True}


def delete_event(event_id: str, calendar_id: str = "primary") -> dict[str, bool]:
    """Delete a calendar event by ID."""
    service = _calendar_service()
    service.events().delete(calendarId=calendar_id, eventId=event_id).execute()
    return {"deleted": True, "event_id": event_id}


# ── Tool manifest (used by the agent to describe available tools) ──────────────
CALENDAR_TOOLS = [
    {
        "name": "list_events",
        "description": "List upcoming Google Calendar events",
        "parameters": {
            "time_min": "ISO 8601 start datetime filter (optional)",
            "time_max": "ISO 8601 end datetime filter (optional)",
            "max_results": "Max number of events (default 10)",
        },
        "fn": list_events,
    },
    {
        "name": "create_event",
        "description": "Create a new Google Calendar event",
        "parameters": {
            "summary": "Event title (required)",
            "start_datetime": "ISO 8601 start datetime (required)",
            "end_datetime": "ISO 8601 end datetime (required)",
            "description": "Event notes (optional)",
            "location": "Event location (optional)",
        },
        "fn": create_event,
    },
    {
        "name": "update_event",
        "description": "Update an existing calendar event by ID",
        "parameters": {"event_id": "required", "summary": "opt", "start_datetime": "opt"},
        "fn": update_event,
    },
    {
        "name": "delete_event",
        "description": "Delete a calendar event by ID",
        "parameters": {"event_id": "required"},
        "fn": delete_event,
    },
]
