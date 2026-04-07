"""
Unit tests for the Agentic AI Google Ecosystem.

These tests do NOT require real Google credentials, a live Gemini API key,
or a running AlloyDB instance – all external I/O is mocked.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest


# ============================================================
# Helpers
# ============================================================

def _make_mock_service_events(events: list[dict]):
    """Return a mock Google Calendar service whose events().list() returns *events*."""
    svc = MagicMock()
    svc.events.return_value.list.return_value.execute.return_value = {"items": events}
    svc.events.return_value.insert.return_value.execute.return_value = events[0] if events else {}
    svc.events.return_value.get.return_value.execute.return_value = events[0] if events else {}
    svc.events.return_value.update.return_value.execute.return_value = events[0] if events else {}
    svc.events.return_value.delete.return_value.execute.return_value = None
    return svc


def _make_mock_tasks_service(tasks: list[dict]):
    """Return a mock Google Tasks service."""
    svc = MagicMock()
    svc.tasklists.return_value.list.return_value.execute.return_value = {
        "items": [{"id": "tl1", "title": "Notes"}]
    }
    svc.tasks.return_value.list.return_value.execute.return_value = {"items": tasks}
    svc.tasks.return_value.insert.return_value.execute.return_value = tasks[0] if tasks else {}
    svc.tasks.return_value.get.return_value.execute.return_value = tasks[0] if tasks else {}
    svc.tasks.return_value.update.return_value.execute.return_value = tasks[0] if tasks else {}
    svc.tasks.return_value.delete.return_value.execute.return_value = None
    return svc


# ============================================================
# Config settings tests
# ============================================================

class TestSettings:
    def test_default_gemini_model(self):
        from config.settings import Settings

        s = Settings()
        assert s.gemini_model == "gemini-2.0-flash"

    def test_default_log_level(self):
        from config.settings import Settings

        s = Settings()
        assert s.log_level == "INFO"

    def test_env_override(self, monkeypatch):
        monkeypatch.setenv("GEMINI_MODEL", "gemini-1.5-pro")
        from config.settings import Settings

        s = Settings()
        assert s.gemini_model == "gemini-1.5-pro"


# ============================================================
# Calendar tool tests
# ============================================================

class TestCalendarTool:
    """Tests for tools/calendar_tool.py (Google Calendar service is mocked)."""

    _SAMPLE_EVENTS = [
        {
            "id": "event1",
            "summary": "Team standup",
            "description": "Daily sync",
            "location": "Zoom",
            "start": {"dateTime": "2024-05-01T09:00:00Z"},
            "end": {"dateTime": "2024-05-01T09:30:00Z"},
            "attendees": [{"email": "alice@example.com"}],
            "htmlLink": "https://calendar.google.com/event?eid=event1",
        }
    ]

    def test_list_calendar_events_returns_events(self):
        from tools import calendar_tool

        with patch.object(
            calendar_tool, "_get_calendar_service", return_value=_make_mock_service_events(self._SAMPLE_EVENTS)
        ):
            result = calendar_tool.list_calendar_events(max_results=5)

        assert result["count"] == 1
        assert result["events"][0]["title"] == "Team standup"
        assert result["events"][0]["id"] == "event1"

    def test_list_calendar_events_empty(self):
        from tools import calendar_tool

        with patch.object(
            calendar_tool, "_get_calendar_service", return_value=_make_mock_service_events([])
        ):
            result = calendar_tool.list_calendar_events()

        assert result["count"] == 0
        assert result["events"] == []

    def test_create_calendar_event(self):
        from tools import calendar_tool

        mock_svc = _make_mock_service_events(self._SAMPLE_EVENTS)
        mock_svc.events.return_value.insert.return_value.execute.return_value = {
            "id": "new_event",
            "summary": "New meeting",
            "start": {"dateTime": "2024-05-02T10:00:00Z"},
            "end": {"dateTime": "2024-05-02T11:00:00Z"},
            "htmlLink": "https://calendar.google.com/event?eid=new_event",
        }

        with patch.object(calendar_tool, "_get_calendar_service", return_value=mock_svc):
            result = calendar_tool.create_calendar_event(
                title="New meeting",
                start_time="2024-05-02T10:00:00Z",
                end_time="2024-05-02T11:00:00Z",
            )

        assert result["status"] == "created"
        assert result["id"] == "new_event"

    def test_delete_calendar_event(self):
        from tools import calendar_tool

        mock_svc = _make_mock_service_events([])
        with patch.object(calendar_tool, "_get_calendar_service", return_value=mock_svc):
            result = calendar_tool.delete_calendar_event("event1")

        assert result["status"] == "deleted"
        assert result["event_id"] == "event1"

    def test_get_calendar_event(self):
        from tools import calendar_tool

        mock_svc = _make_mock_service_events(self._SAMPLE_EVENTS)
        with patch.object(calendar_tool, "_get_calendar_service", return_value=mock_svc):
            result = calendar_tool.get_calendar_event("event1")

        assert result["id"] == "event1"
        assert result["title"] == "Team standup"

    def test_list_calendar_events_handles_exception(self):
        from tools import calendar_tool

        with patch.object(calendar_tool, "_get_calendar_service", side_effect=Exception("API error")):
            result = calendar_tool.list_calendar_events()

        assert "error" in result
        assert result["count"] == 0


# ============================================================
# Notes tool tests
# ============================================================

class TestNotesTool:
    """Tests for tools/notes_tool.py (Google Tasks service is mocked)."""

    _SAMPLE_TASKS = [
        {
            "id": "task1",
            "title": "Buy groceries",
            "notes": "Milk, eggs, bread",
            "due": None,
            "status": "needsAction",
            "updated": "2024-05-01T08:00:00Z",
        }
    ]

    def test_list_notes(self):
        from tools import notes_tool

        with patch.object(
            notes_tool, "_get_tasks_service", return_value=_make_mock_tasks_service(self._SAMPLE_TASKS)
        ):
            result = notes_tool.list_notes()

        assert result["count"] == 1
        assert result["notes"][0]["title"] == "Buy groceries"

    def test_create_note(self):
        from tools import notes_tool

        mock_svc = _make_mock_tasks_service([])
        mock_svc.tasks.return_value.insert.return_value.execute.return_value = {
            "id": "new_note",
            "title": "Shopping list",
            "notes": "Apples, oranges",
        }

        with patch.object(notes_tool, "_get_tasks_service", return_value=mock_svc):
            result = notes_tool.create_note(title="Shopping list", content="Apples, oranges")

        assert result["status"] == "created"
        assert result["id"] == "new_note"

    def test_search_notes_filters_by_keyword(self):
        from tools import notes_tool

        tasks = [
            {"id": "t1", "title": "Buy groceries", "notes": "Milk, eggs", "due": None, "status": "needsAction", "updated": "2024-05-01T08:00:00Z"},
            {"id": "t2", "title": "Doctor appointment", "notes": "At 3pm", "due": None, "status": "needsAction", "updated": "2024-05-01T09:00:00Z"},
        ]

        with patch.object(
            notes_tool, "_get_tasks_service", return_value=_make_mock_tasks_service(tasks)
        ):
            result = notes_tool.search_notes("groceries")

        assert result["count"] == 1
        assert result["notes"][0]["title"] == "Buy groceries"

    def test_delete_note(self):
        from tools import notes_tool

        mock_svc = _make_mock_tasks_service([])
        with patch.object(notes_tool, "_get_tasks_service", return_value=mock_svc):
            result = notes_tool.delete_note("task1")

        assert result["status"] == "deleted"


# ============================================================
# Maps tool tests
# ============================================================

class TestMapsTool:
    """Tests for tools/maps_tool.py (googlemaps client is mocked)."""

    def _mock_gmaps(self):
        """Return a MagicMock mimicking a googlemaps.Client."""
        client = MagicMock()
        client.geocode.return_value = [
            {
                "place_id": "ChIJ_abc",
                "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
                "geometry": {"location": {"lat": 37.4224764, "lng": -122.0842499}},
            }
        ]
        client.reverse_geocode.return_value = [
            {
                "place_id": "ChIJ_abc",
                "formatted_address": "1600 Amphitheatre Pkwy, Mountain View, CA 94043, USA",
                "address_components": [],
            }
        ]
        client.places.return_value = {"results": []}
        client.directions.return_value = [
            {
                "legs": [
                    {
                        "start_address": "Origin",
                        "end_address": "Destination",
                        "distance": {"text": "10 km"},
                        "duration": {"text": "15 mins"},
                        "steps": [],
                    }
                ],
                "summary": "Via Main St",
            }
        ]
        client.distance_matrix.return_value = {
            "origin_addresses": ["Origin"],
            "destination_addresses": ["Destination"],
            "rows": [
                {
                    "elements": [
                        {
                            "distance": {"text": "10 km"},
                            "duration": {"text": "15 mins"},
                            "status": "OK",
                        }
                    ]
                }
            ],
        }
        return client

    def test_geocode_address(self):
        from tools import maps_tool

        with patch.object(maps_tool, "_get_maps_client", return_value=self._mock_gmaps()):
            result = maps_tool.geocode_address("Googleplex, Mountain View")

        assert result["lat"] == pytest.approx(37.4224764)
        assert "formatted_address" in result

    def test_geocode_address_no_results(self):
        from tools import maps_tool

        mock_client = self._mock_gmaps()
        mock_client.geocode.return_value = []
        with patch.object(maps_tool, "_get_maps_client", return_value=mock_client):
            result = maps_tool.geocode_address("xyzzy nowhere")

        assert "error" in result

    def test_reverse_geocode(self):
        from tools import maps_tool

        with patch.object(maps_tool, "_get_maps_client", return_value=self._mock_gmaps()):
            result = maps_tool.reverse_geocode(37.4224764, -122.0842499)

        assert "formatted_address" in result

    def test_get_directions(self):
        from tools import maps_tool

        with patch.object(maps_tool, "_get_maps_client", return_value=self._mock_gmaps()):
            result = maps_tool.get_directions("Origin", "Destination")

        assert result["distance"] == "10 km"
        assert result["duration"] == "15 mins"

    def test_get_distance_matrix(self):
        from tools import maps_tool

        with patch.object(maps_tool, "_get_maps_client", return_value=self._mock_gmaps()):
            result = maps_tool.get_distance_matrix(["Origin"], ["Destination"])

        assert result["matrix"][0][0]["distance"] == "10 km"

    def test_maps_tool_handles_exception(self):
        from tools import maps_tool

        with patch.object(maps_tool, "_get_maps_client", side_effect=Exception("Network error")):
            result = maps_tool.geocode_address("anywhere")

        assert "error" in result


# ============================================================
# Database model tests
# ============================================================

class TestDatabaseModels:
    """Smoke-tests for ORM model instantiation."""

    def test_user_creation(self):
        from database.models import User

        user = User(email="test@example.com", display_name="Test User")
        assert user.email == "test@example.com"
        assert user.display_name == "Test User"

    def test_task_creation(self):
        from database.models import Task

        task = Task(user_id="uid-123", title="Buy milk", priority="high")
        assert task.title == "Buy milk"
        assert task.priority == "high"
        # is_completed starts as None at Python level; the DB default (False) is applied on INSERT
        assert task.is_completed in (False, None)

    def test_calendar_event_creation(self):
        from database.models import CalendarEvent

        event = CalendarEvent(
            user_id="uid-123",
            title="Meeting",
            start_time=datetime(2024, 5, 1, 9, 0, tzinfo=timezone.utc),
        )
        assert event.title == "Meeting"

    def test_note_creation(self):
        from database.models import Note

        note = Note(user_id="uid-123", title="Ideas", content="Some cool ideas")
        assert note.content == "Some cool ideas"

    def test_location_creation(self):
        from database.models import Location

        loc = Location(user_id="uid-123", name="Home", address="123 Main St")
        assert loc.name == "Home"

    def test_agent_session_creation(self):
        from database.models import AgentSession

        session = AgentSession(id="sess-abc")
        assert session.id == "sess-abc"

    def test_agent_message_creation(self):
        from database.models import AgentMessage

        msg = AgentMessage(session_id="sess-abc", role="user", content="Hello")
        assert msg.role == "user"
        assert msg.content == "Hello"


# ============================================================
# AlloyDB client tests
# ============================================================

class TestAlloyDBClient:
    """Tests for database/alloydb_client.py – no live DB required."""

    @pytest.mark.asyncio
    async def test_init_falls_back_to_sqlite_when_no_config(self, monkeypatch):
        """When no DATABASE_URL or ALLOYDB config is set, a SQLite URL is used."""
        from config.settings import Settings
        import database.alloydb_client as alloydb_module

        # Patch settings so no DB config is present
        mock_settings = Settings(
            GOOGLE_API_KEY="",
            DATABASE_URL="",
            ALLOYDB_INSTANCE_URI="",
        )
        monkeypatch.setattr(alloydb_module, "settings", mock_settings)

        from database.alloydb_client import AlloyDBClient

        client = AlloyDBClient()
        url = await client._build_url()
        assert "sqlite" in url

    @pytest.mark.asyncio
    async def test_init_uses_database_url_when_provided(self, monkeypatch):
        from config.settings import Settings
        import database.alloydb_client as alloydb_module

        mock_settings = Settings(
            GOOGLE_API_KEY="",
            DATABASE_URL="postgresql+asyncpg://user:pass@localhost/test",
        )
        monkeypatch.setattr(alloydb_module, "settings", mock_settings)

        from database.alloydb_client import AlloyDBClient

        client = AlloyDBClient()
        url = await client._build_url()
        assert url == "postgresql+asyncpg://user:pass@localhost/test"


# ============================================================
# Orchestrator routing tests (Gemini is mocked)
# ============================================================

class TestOrchestratorRouting:
    """Verify that the orchestrator correctly routes messages to the right domain."""

    def _make_gemini_response(self, text: str):
        """Create a minimal mock for a Gemini response object."""
        part = MagicMock()
        part.text = text
        part.function_call.name = ""  # no function call

        candidate = MagicMock()
        candidate.content.parts = [part]

        response = MagicMock()
        response.candidates = [candidate]
        response.text = text
        return response

    def _patch_google(self, monkeypatch):
        """
        Inject a fake `google.generativeai` module so agent imports succeed
        without requiring the real SDK to be installed.
        """
        import sys
        import types

        google_ns = types.ModuleType("google")
        genai_mod = types.ModuleType("google.generativeai")
        protos_mod = types.ModuleType("google.generativeai.protos")

        # Minimal stubs used at import / class-body evaluation time
        genai_mod.configure = MagicMock()
        genai_mod.GenerativeModel = MagicMock()
        genai_mod.protos = protos_mod
        genai_mod.protos.Part = MagicMock()
        genai_mod.protos.FunctionResponse = MagicMock()

        # FunctionDeclaration / Tool stubs
        genai_types_mod = types.ModuleType("google.generativeai.types")
        genai_types_mod.FunctionDeclaration = MagicMock(side_effect=lambda **kw: MagicMock())
        genai_types_mod.Tool = MagicMock(side_effect=lambda **kw: MagicMock())
        genai_mod.types = genai_types_mod

        monkeypatch.setitem(sys.modules, "google", google_ns)
        monkeypatch.setitem(sys.modules, "google.generativeai", genai_mod)
        monkeypatch.setitem(sys.modules, "google.generativeai.types", genai_types_mod)
        monkeypatch.setitem(sys.modules, "google.generativeai.protos", protos_mod)

        return genai_mod

    @pytest.mark.asyncio
    async def test_classify_calendar(self, monkeypatch):
        """Messages about events should be classified as 'calendar'."""
        import sys
        # Remove cached agent modules so they re-import with mocked google
        for mod in list(sys.modules):
            if mod.startswith("agents"):
                monkeypatch.delitem(sys.modules, mod, raising=False)

        genai_mod = self._patch_google(monkeypatch)

        from agents import orchestrator as orch_module

        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        agent = orch_module.OrchestratorAgent(db=db)

        mock_router = MagicMock()
        mock_router.generate_content.return_value = self._make_gemini_response("calendar")
        agent._router = mock_router

        domain = await agent._classify("Schedule a meeting for tomorrow at 3pm")
        assert domain == "calendar"

    @pytest.mark.asyncio
    async def test_classify_maps(self, monkeypatch):
        import sys
        for mod in list(sys.modules):
            if mod.startswith("agents"):
                monkeypatch.delitem(sys.modules, mod, raising=False)

        self._patch_google(monkeypatch)
        from agents import orchestrator as orch_module

        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        agent = orch_module.OrchestratorAgent(db=db)
        mock_router = MagicMock()
        mock_router.generate_content.return_value = self._make_gemini_response("maps")
        agent._router = mock_router

        domain = await agent._classify("How do I get to the nearest coffee shop?")
        assert domain == "maps"

    @pytest.mark.asyncio
    async def test_classify_notes(self, monkeypatch):
        import sys
        for mod in list(sys.modules):
            if mod.startswith("agents"):
                monkeypatch.delitem(sys.modules, mod, raising=False)

        self._patch_google(monkeypatch)
        from agents import orchestrator as orch_module

        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        agent = orch_module.OrchestratorAgent(db=db)
        mock_router = MagicMock()
        mock_router.generate_content.return_value = self._make_gemini_response("notes")
        agent._router = mock_router

        domain = await agent._classify("Save a note about the project requirements")
        assert domain == "notes"

    @pytest.mark.asyncio
    async def test_classify_tasks(self, monkeypatch):
        import sys
        for mod in list(sys.modules):
            if mod.startswith("agents"):
                monkeypatch.delitem(sys.modules, mod, raising=False)

        self._patch_google(monkeypatch)
        from agents import orchestrator as orch_module

        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        agent = orch_module.OrchestratorAgent(db=db)
        mock_router = MagicMock()
        mock_router.generate_content.return_value = self._make_gemini_response("tasks")
        agent._router = mock_router

        domain = await agent._classify("Add 'review PR' to my task list")
        assert domain == "tasks"

    @pytest.mark.asyncio
    async def test_classify_falls_back_to_general_on_unknown(self, monkeypatch):
        import sys
        for mod in list(sys.modules):
            if mod.startswith("agents"):
                monkeypatch.delitem(sys.modules, mod, raising=False)

        self._patch_google(monkeypatch)
        from agents import orchestrator as orch_module

        db = AsyncMock()
        db.execute.return_value.scalar_one_or_none.return_value = MagicMock()

        agent = orch_module.OrchestratorAgent(db=db)
        mock_router = MagicMock()
        mock_router.generate_content.return_value = self._make_gemini_response("something_else")
        agent._router = mock_router

        domain = await agent._classify("Tell me a joke")
        assert domain == "general"
