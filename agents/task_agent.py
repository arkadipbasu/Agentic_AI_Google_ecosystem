"""
Task Agent – manages user tasks (stored in AlloyDB) with optional Google Tasks sync.

In addition to the tasks stored in AlloyDB, this agent can create/update
Google Tasks entries to keep the two stores in sync.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import google.generativeai as genai
from google.generativeai.types import FunctionDeclaration, Tool
from sqlalchemy import select, update as sa_update
from sqlalchemy.ext.asyncio import AsyncSession

from config.settings import settings
from database.models import Task, User

logger = logging.getLogger(__name__)

AGENT_NAME = "task_agent"

SYSTEM_PROMPT = """\
You are a helpful task management assistant. You help users create, track,
update, and complete tasks. Always confirm task details before creating them
and provide clear summaries of what was done. Prioritise tasks by urgency
when listing them.
"""


# ---------------------------------------------------------------------------
# Local (AlloyDB) task CRUD helpers
# ---------------------------------------------------------------------------

async def _db_list_tasks(
    db: AsyncSession,
    user_id: str,
    include_completed: bool = False,
) -> list[dict[str, Any]]:
    stmt = select(Task).where(Task.user_id == user_id)
    if not include_completed:
        stmt = stmt.where(Task.is_completed == False)  # noqa: E712
    result = await db.execute(stmt)
    tasks = result.scalars().all()
    return [
        {
            "id": t.id,
            "title": t.title,
            "description": t.description,
            "due_date": t.due_date.isoformat() if t.due_date else None,
            "priority": t.priority,
            "is_completed": t.is_completed,
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in tasks
    ]


async def _db_create_task(
    db: AsyncSession,
    user_id: str,
    title: str,
    description: str | None = None,
    due_date: str | None = None,
    priority: str = "medium",
) -> dict[str, Any]:
    due_dt = datetime.fromisoformat(due_date) if due_date else None
    task = Task(
        user_id=user_id,
        title=title,
        description=description,
        due_date=due_dt,
        priority=priority,
    )
    db.add(task)
    await db.flush()
    return {
        "id": task.id,
        "title": task.title,
        "description": task.description,
        "due_date": task.due_date.isoformat() if task.due_date else None,
        "priority": task.priority,
        "status": "created",
    }


async def _db_complete_task(
    db: AsyncSession, user_id: str, task_id: str
) -> dict[str, Any]:
    stmt = (
        sa_update(Task)
        .where(Task.id == task_id, Task.user_id == user_id)
        .values(is_completed=True)
        .returning(Task.id, Task.title)
    )
    result = await db.execute(stmt)
    row = result.first()
    if row:
        return {"id": row[0], "title": row[1], "status": "completed"}
    return {"error": "Task not found.", "task_id": task_id}


async def _db_delete_task(
    db: AsyncSession, user_id: str, task_id: str
) -> dict[str, Any]:
    stmt = select(Task).where(Task.id == task_id, Task.user_id == user_id)
    result = await db.execute(stmt)
    task = result.scalar_one_or_none()
    if task is None:
        return {"error": "Task not found.", "task_id": task_id}
    await db.delete(task)
    return {"status": "deleted", "task_id": task_id}


# ---------------------------------------------------------------------------
# Gemini function declarations (operating on a user context)
# ---------------------------------------------------------------------------

_LIST_TASKS = FunctionDeclaration(
    name="list_tasks",
    description="List the user's tasks.",
    parameters={
        "type": "object",
        "properties": {
            "include_completed": {
                "type": "boolean",
                "description": "Include completed tasks (default false)",
            }
        },
    },
)

_CREATE_TASK = FunctionDeclaration(
    name="create_task",
    description="Create a new task for the user.",
    parameters={
        "type": "object",
        "required": ["title"],
        "properties": {
            "title": {"type": "string"},
            "description": {"type": "string"},
            "due_date": {"type": "string", "description": "ISO 8601 due date"},
            "priority": {
                "type": "string",
                "enum": ["low", "medium", "high"],
                "description": "Task priority",
            },
        },
    },
)

_COMPLETE_TASK = FunctionDeclaration(
    name="complete_task",
    description="Mark a task as completed.",
    parameters={
        "type": "object",
        "required": ["task_id"],
        "properties": {"task_id": {"type": "string"}},
    },
)

_DELETE_TASK = FunctionDeclaration(
    name="delete_task",
    description="Delete a task.",
    parameters={
        "type": "object",
        "required": ["task_id"],
        "properties": {"task_id": {"type": "string"}},
    },
)

TASK_TOOLS = Tool(
    function_declarations=[
        _LIST_TASKS,
        _CREATE_TASK,
        _COMPLETE_TASK,
        _DELETE_TASK,
    ]
)


# ---------------------------------------------------------------------------
# Agent class
# ---------------------------------------------------------------------------

class TaskAgent:
    """
    Gemini-powered task management agent backed by AlloyDB.

    A database session and user_id must be provided at construction time so
    the agent can persist tasks.
    """

    def __init__(self, db: AsyncSession, user_id: str) -> None:
        self._db = db
        self._user_id = user_id
        if settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)
        self._model = genai.GenerativeModel(
            model_name=settings.gemini_model,
            system_instruction=SYSTEM_PROMPT,
            tools=[TASK_TOOLS],
        )
        self._chat = self._model.start_chat(enable_automatic_function_calling=False)

    async def chat(self, user_message: str) -> str:
        """Process a user message asynchronously and return the agent's response."""
        response = self._chat.send_message(user_message)
        return await self._process_response(response)

    async def _process_response(self, response) -> str:
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
                return "I've completed the requested task operation."

            fn_responses = []
            for fn_call in fn_calls:
                fn_name = fn_call.name
                fn_args = dict(fn_call.args)
                logger.debug("TaskAgent calling %s(%s)", fn_name, fn_args)
                result = await self._dispatch(fn_name, fn_args)
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

    async def _dispatch(self, fn_name: str, fn_args: dict) -> dict[str, Any]:
        """Route function call to the appropriate DB helper."""
        if fn_name == "list_tasks":
            return await _db_list_tasks(
                self._db,
                self._user_id,
                include_completed=fn_args.get("include_completed", False),
            )
        if fn_name == "create_task":
            return await _db_create_task(
                self._db,
                self._user_id,
                title=fn_args["title"],
                description=fn_args.get("description"),
                due_date=fn_args.get("due_date"),
                priority=fn_args.get("priority", "medium"),
            )
        if fn_name == "complete_task":
            return await _db_complete_task(self._db, self._user_id, fn_args["task_id"])
        if fn_name == "delete_task":
            return await _db_delete_task(self._db, self._user_id, fn_args["task_id"])
        return {"error": f"Unknown function: {fn_name}"}
