"""
agents/notes_agent.py
"""
from agents.base_agent import BaseAgent
from tools.notes_tool import NOTES_TOOLS


class NotesAgent(BaseAgent):
    name = "notes"
    system_prompt = (
        "You are a Google Keep notes assistant. Help users create, search, update "
        "and delete notes. Summarise actions clearly after each operation."
    )
    tools_manifest = NOTES_TOOLS

    def describe(self) -> str:
        return "Handles Google Keep notes: list, create, update, search, delete."


# ─────────────────────────────────────────────────────────────────────────────

"""
agents/maps_agent.py
"""
from agents.base_agent import BaseAgent
from tools.maps_tool import MAPS_TOOLS


class MapsAgent(BaseAgent):
    name = "maps"
    system_prompt = (
        "You are a Google Maps assistant. Help users find places, get directions, "
        "calculate distances, and geocode addresses. Present results clearly."
    )
    tools_manifest = MAPS_TOOLS

    def describe(self) -> str:
        return "Handles Google Maps: geocode, place search, directions, distance matrix."


# ─────────────────────────────────────────────────────────────────────────────

"""
agents/tasks_agent.py
"""
from agents.base_agent import BaseAgent
from tools.tasks_tool import TASKS_TOOLS


class TasksAgent(BaseAgent):
    name = "tasks"
    system_prompt = (
        "You are a Google Tasks assistant. Help users manage their task lists: "
        "create tasks, mark them complete, update due dates, and delete tasks."
    )
    tools_manifest = TASKS_TOOLS

    def describe(self) -> str:
        return "Handles Google Tasks: list task lists, create, complete, update, delete tasks."
