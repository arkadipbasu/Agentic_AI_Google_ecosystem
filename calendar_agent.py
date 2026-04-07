"""
agents/calendar_agent.py
"""
from agents.base_agent import BaseAgent
from tools.calendar_tool import CALENDAR_TOOLS


class CalendarAgent(BaseAgent):
    name = "calendar"
    system_prompt = (
        "You are a Google Calendar assistant. Use the available tools to list, "
        "create, update, or delete calendar events based on the user's request. "
        "Always confirm actions with a brief natural-language summary."
    )
    tools_manifest = CALENDAR_TOOLS

    def describe(self) -> str:
        return "Handles Google Calendar: list, create, update, delete events."
