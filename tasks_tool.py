"""
tools/tasks_tool.py
MCP-style wrapper around the Google Tasks API v1.
"""

from typing import Any

from google.oauth2 import service_account
from googleapiclient.discovery import build

from config import get_settings

SCOPES = ["https://www.googleapis.com/auth/tasks"]


def _tasks_service():
    settings = get_settings()
    creds = service_account.Credentials.from_service_account_file(
        settings.GOOGLE_SA_KEY_PATH, scopes=SCOPES
    )
    return build("tasks", "v1", credentials=creds, cache_discovery=False)


# ── Tools ─────────────────────────────────────────────────────────────────────

def list_tasklists() -> list[dict[str, Any]]:
    """Return all task lists for the authenticated account."""
    result = _tasks_service().tasklists().list().execute()
    return [{"id": tl["id"], "title": tl["title"]} for tl in result.get("items", [])]


def list_tasks(tasklist_id: str = "@default", show_completed: bool = False) -> list[dict[str, Any]]:
    """Return tasks in a task list."""
    result = (
        _tasks_service()
        .tasks()
        .list(tasklist=tasklist_id, showCompleted=show_completed)
        .execute()
    )
    return [
        {
            "id": t["id"],
            "title": t.get("title", ""),
            "notes": t.get("notes", ""),
            "due": t.get("due"),
            "status": t.get("status", "needsAction"),
        }
        for t in result.get("items", [])
    ]


def create_task(
    title: str,
    notes: str = "",
    due: str | None = None,           # RFC 3339 timestamp
    tasklist_id: str = "@default",
) -> dict[str, Any]:
    """Create a new task."""
    body: dict[str, Any] = {"title": title, "notes": notes}
    if due:
        body["due"] = due
    task = _tasks_service().tasks().insert(tasklist=tasklist_id, body=body).execute()
    return {"id": task["id"], "title": title, "created": True}


def complete_task(task_id: str, tasklist_id: str = "@default") -> dict[str, Any]:
    """Mark a task as completed."""
    service = _tasks_service()
    task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
    task["status"] = "completed"
    updated = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
    return {"id": updated["id"], "status": "completed"}


def delete_task(task_id: str, tasklist_id: str = "@default") -> dict[str, Any]:
    """Permanently delete a task."""
    _tasks_service().tasks().delete(tasklist=tasklist_id, task=task_id).execute()
    return {"id": task_id, "deleted": True}


def update_task(
    task_id: str,
    title: str | None = None,
    notes: str | None = None,
    due: str | None = None,
    tasklist_id: str = "@default",
) -> dict[str, Any]:
    """Update fields of an existing task."""
    service = _tasks_service()
    task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
    if title:
        task["title"] = title
    if notes is not None:
        task["notes"] = notes
    if due is not None:
        task["due"] = due
    updated = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
    return {"id": updated["id"], "updated": True}


# ── Tool manifest ─────────────────────────────────────────────────────────────
TASKS_TOOLS = [
    {"name": "list_tasklists", "description": "List all task lists",        "fn": list_tasklists},
    {"name": "list_tasks",     "description": "List tasks in a task list",  "fn": list_tasks},
    {"name": "create_task",    "description": "Create a new task",           "fn": create_task},
    {"name": "complete_task",  "description": "Mark a task as completed",    "fn": complete_task},
    {"name": "delete_task",    "description": "Delete a task permanently",   "fn": delete_task},
    {"name": "update_task",    "description": "Update task fields",          "fn": update_task},
]
