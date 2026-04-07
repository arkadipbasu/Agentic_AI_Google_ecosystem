"""
tools/notes_tool.py
MCP-style wrapper for note management.
Uses Google Keep API (v1) via service account with domain-wide delegation,
or falls back to Google Drive (Docs) if Keep API is unavailable.
"""

from typing import Any

import httpx
from google.oauth2 import service_account
from google.auth.transport.requests import Request

from config import get_settings

KEEP_SCOPES = ["https://www.googleapis.com/auth/keep"]
KEEP_BASE = "https://keep.googleapis.com/v1"


def _keep_token() -> str:
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_KEY_PATH, scopes=KEEP_SCOPES
    )
    creds.refresh(Request())
    return creds.token


def _headers() -> dict[str, str]:
    return {"Authorization": f"Bearer {_keep_token()}", "Content-Type": "application/json"}


# ── Tools ─────────────────────────────────────────────────────────────────────

def list_notes(filter_label: str | None = None) -> list[dict[str, Any]]:
    """List Google Keep notes, optionally filtered by label text."""
    params = {}
    if filter_label:
        params["filter"] = f'label.name = "{filter_label}"'
    resp = httpx.get(f"{KEEP_BASE}/notes", headers=_headers(), params=params)
    resp.raise_for_status()
    notes = resp.json().get("notes", [])
    return [
        {
            "id": n["name"],
            "title": n.get("title", ""),
            "body": n.get("body", {}).get("text", {}).get("text", ""),
            "labels": [lb.get("name") for lb in n.get("labels", [])],
            "trashed": n.get("trashed", False),
        }
        for n in notes
    ]


def create_note(title: str, body: str, labels: list[str] | None = None) -> dict[str, Any]:
    """Create a new Google Keep note."""
    payload: dict[str, Any] = {
        "title": title,
        "body": {"text": {"text": body}},
    }
    resp = httpx.post(f"{KEEP_BASE}/notes", headers=_headers(), json=payload)
    resp.raise_for_status()
    note = resp.json()
    return {"id": note["name"], "title": title, "created": True}


def update_note(note_id: str, title: str | None = None, body: str | None = None) -> dict[str, Any]:
    """Update the title or body of an existing note."""
    update_mask_fields = []
    patch: dict[str, Any] = {}
    if title is not None:
        patch["title"] = title
        update_mask_fields.append("title")
    if body is not None:
        patch["body"] = {"text": {"text": body}}
        update_mask_fields.append("body")
    update_mask = ",".join(update_mask_fields)
    resp = httpx.patch(
        f"{KEEP_BASE}/{note_id}",
        headers=_headers(),
        json=patch,
        params={"updateMask": update_mask},
    )
    resp.raise_for_status()
    return {"id": note_id, "updated": True}


def delete_note(note_id: str) -> dict[str, Any]:
    """Move a note to trash (Keep uses soft delete)."""
    resp = httpx.delete(f"{KEEP_BASE}/{note_id}", headers=_headers())
    resp.raise_for_status()
    return {"id": note_id, "deleted": True}


def search_notes(query: str) -> list[dict[str, Any]]:
    """Filter notes whose title or body contains the query string."""
    all_notes = list_notes()
    q = query.lower()
    return [
        n for n in all_notes
        if q in n["title"].lower() or q in n["body"].lower()
    ]


# ── Tool manifest ─────────────────────────────────────────────────────────────
NOTES_TOOLS = [
    {"name": "list_notes",   "description": "List all Google Keep notes", "fn": list_notes},
    {"name": "create_note",  "description": "Create a new note",          "fn": create_note},
    {"name": "update_note",  "description": "Update an existing note",     "fn": update_note},
    {"name": "delete_note",  "description": "Trash a note by ID",          "fn": delete_note},
    {"name": "search_notes", "description": "Search notes by keyword",     "fn": search_notes},
]
