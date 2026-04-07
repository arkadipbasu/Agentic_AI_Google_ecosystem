"""
Orchestrator Agent – routes user requests to the appropriate specialist agent.

The orchestrator uses Gemini to understand the user's intent and delegates:
  - Calendar-related requests  → CalendarAgent
  - Notes/knowledge requests   → NotesAgent
  - Location/maps requests     → MapsAgent
  - Task management requests   → TaskAgent
  - Cross-domain requests      → handled by combining multiple agents

It also:
  - Persists conversation history to AlloyDB (agent_sessions / agent_messages)
  - Retrieves tasks/notes/events context to enrich responses
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import google.generativeai as genai
from sqlalchemy.ext.asyncio import AsyncSession

from agents.calendar_agent import CalendarAgent
from agents.maps_agent import MapsAgent
from agents.notes_agent import NotesAgent
from agents.task_agent import TaskAgent
from config.settings import settings
from database.models import AgentMessage, AgentSession

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are a smart personal assistant that helps users manage their schedule,
tasks, notes, and location information using the Google ecosystem.

You coordinate the following specialist agents:
  - **calendar_agent**: Manages Google Calendar events (list, create, update, delete)
  - **notes_agent**: Manages notes via Google Tasks (list, create, update, search)
  - **maps_agent**: Answers location queries (directions, place search, geocoding)
  - **task_agent**: Manages tasks stored in the database (list, create, complete, delete)

Routing guidelines:
  - "schedule", "event", "meeting", "appointment", "calendar" → calendar_agent
  - "note", "reminder", "save this", "write down", "remember" → notes_agent
  - "directions", "place", "restaurant", "distance", "where is", "map" → maps_agent
  - "task", "to-do", "todo", "deadline", "priority" → task_agent
  - If the request spans multiple domains, handle each part with the right agent
    and combine the responses.

Always be concise, helpful, and proactive. If you're unsure which agent to use,
ask the user a clarifying question.
"""

_ROUTING_PROMPT_TEMPLATE = """\
Classify the following user message into ONE of these categories:
  calendar, notes, maps, tasks, general

User message: "{message}"

Reply with ONLY the category name (lowercase).
"""


class OrchestratorAgent:
    """
    Top-level multi-agent orchestrator.

    Parameters
    ----------
    db : AsyncSession
        An open AlloyDB/SQLAlchemy async session for persisting conversation history.
    user_id : str | None
        Optional user identifier for personalized context.
    session_id : str | None
        Optional session ID to resume an existing conversation.
    """

    def __init__(
        self,
        db: AsyncSession,
        user_id: str | None = None,
        session_id: str | None = None,
    ) -> None:
        self._db = db
        self._user_id = user_id or "anonymous"
        self._session_id = session_id or str(uuid.uuid4())

        if settings.google_api_key:
            genai.configure(api_key=settings.google_api_key)

        # Routing model (lightweight, no tools)
        self._router = genai.GenerativeModel(model_name=settings.gemini_model)

        # Specialist agents (instantiated lazily)
        self._calendar: CalendarAgent | None = None
        self._notes: NotesAgent | None = None
        self._maps: MapsAgent | None = None
        self._tasks: TaskAgent | None = None

    # ------------------------------------------------------------------ #
    # Public interface
    # ------------------------------------------------------------------ #

    async def chat(self, user_message: str) -> str:
        """
        Process a user message, route it to the appropriate agent(s),
        persist the exchange, and return the final response.
        """
        await self._persist_message("user", user_message)

        domain = await self._classify(user_message)
        logger.info("Routing '%s' to domain: %s", user_message[:60], domain)

        response = await self._dispatch(domain, user_message)

        await self._persist_message("assistant", response, agent_name=domain)
        return response

    # ------------------------------------------------------------------ #
    # Private helpers
    # ------------------------------------------------------------------ #

    async def _classify(self, message: str) -> str:
        """Use Gemini to classify the message into a routing domain."""
        prompt = _ROUTING_PROMPT_TEMPLATE.format(message=message)
        try:
            resp = self._router.generate_content(prompt)
            domain = resp.text.strip().lower()
            if domain not in {"calendar", "notes", "maps", "tasks"}:
                domain = "general"
        except Exception as exc:
            logger.warning("Routing classification failed: %s", exc)
            domain = "general"
        return domain

    async def _dispatch(self, domain: str, message: str) -> str:
        """Route the message to the correct specialist agent."""
        if domain == "calendar":
            return await asyncio.to_thread(self._get_calendar_agent().chat, message)
        if domain == "notes":
            return await asyncio.to_thread(self._get_notes_agent().chat, message)
        if domain == "maps":
            return await asyncio.to_thread(self._get_maps_agent().chat, message)
        if domain == "tasks":
            return await self._get_task_agent().chat(message)

        # General: let the main model answer directly
        return await self._general_response(message)

    async def _general_response(self, message: str) -> str:
        """Generate a general response using the main Gemini model."""
        try:
            resp = self._router.generate_content(
                f"{SYSTEM_PROMPT}\n\nUser: {message}"
            )
            return resp.text
        except Exception as exc:
            logger.error("General response failed: %s", exc)
            return (
                "I'm sorry, I encountered an error while processing your request. "
                "Please try again."
            )

    # Lazy agent constructors

    def _get_calendar_agent(self) -> CalendarAgent:
        if self._calendar is None:
            self._calendar = CalendarAgent()
        return self._calendar

    def _get_notes_agent(self) -> NotesAgent:
        if self._notes is None:
            self._notes = NotesAgent()
        return self._notes

    def _get_maps_agent(self) -> MapsAgent:
        if self._maps is None:
            self._maps = MapsAgent()
        return self._maps

    def _get_task_agent(self) -> TaskAgent:
        if self._tasks is None:
            self._tasks = TaskAgent(self._db, self._user_id)
        return self._tasks

    # Persistence helpers

    async def _ensure_session(self) -> None:
        """Create the AgentSession row if it doesn't exist yet."""
        from sqlalchemy import select

        stmt = select(AgentSession).where(AgentSession.id == self._session_id)
        result = await self._db.execute(stmt)
        if result.scalar_one_or_none() is None:
            session_row = AgentSession(
                id=self._session_id,
                user_id=self._user_id if self._user_id != "anonymous" else None,
            )
            self._db.add(session_row)
            await self._db.flush()

    async def _persist_message(
        self, role: str, content: str, agent_name: str | None = None
    ) -> None:
        """Persist a message to AlloyDB."""
        try:
            await self._ensure_session()
            msg = AgentMessage(
                session_id=self._session_id,
                role=role,
                content=content,
                agent_name=agent_name,
            )
            self._db.add(msg)
            await self._db.flush()
        except Exception as exc:
            logger.warning("Failed to persist message: %s", exc)
