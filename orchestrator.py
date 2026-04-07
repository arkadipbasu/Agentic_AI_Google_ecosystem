"""
agents/orchestrator.py
The Orchestrator receives the raw user message, decides which sub-agent(s)
to invoke (using Gemini), dispatches them, and returns a unified response.
"""

import json
import logging
from typing import Any

import vertexai
from vertexai.generative_models import GenerativeModel

from agents.calendar_agent import CalendarAgent
from agents.sub_agents import NotesAgent, MapsAgent, TasksAgent
from config import get_settings

logger = logging.getLogger(__name__)

# ── Registry of sub-agents ────────────────────────────────────────────────────
AGENTS = {
    "calendar": CalendarAgent(),
    "notes":    NotesAgent(),
    "maps":     MapsAgent(),
    "tasks":    TasksAgent(),
}

ROUTING_PROMPT = """
You are an orchestrator for a multi-agent productivity system.
Given the user's message, decide which agent(s) should handle it.
Available agents:
{agent_descriptions}

Respond ONLY with a JSON array of agent names to invoke, e.g. ["calendar"] or ["tasks","notes"].
Invoke multiple agents only when the request explicitly spans domains.
User message: "{message}"
"""


class Orchestrator:
    def __init__(self):
        settings = get_settings()
        vertexai.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
        self._model = GenerativeModel(settings.VERTEX_MODEL)

    def _route(self, user_message: str) -> list[str]:
        """Ask Gemini which agents to invoke. Returns list of agent names."""
        descriptions = "\n".join(
            f"- {name}: {agent.describe()}" for name, agent in AGENTS.items()
        )
        prompt = ROUTING_PROMPT.format(
            agent_descriptions=descriptions, message=user_message
        )
        response = self._model.generate_content(prompt)
        text = response.text.strip().strip("`").strip()
        # Strip markdown json fence if present
        if text.startswith("json"):
            text = text[4:].strip()
        try:
            agents = json.loads(text)
            return [a for a in agents if a in AGENTS]
        except json.JSONDecodeError:
            logger.warning("Routing response not JSON: %s — defaulting to calendar", text)
            return ["calendar"]

    def handle(
        self,
        user_message: str,
        session_context: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Main entry point.
        Returns:
            {
              "routed_to": [...],
              "responses": [{agent, result, tool_called, tool_output}, ...],
              "summary": "..."   # combined natural-language summary
            }
        """
        routed_to = self._route(user_message)
        logger.info("Routing '%s' → %s", user_message[:60], routed_to)

        responses = []
        for agent_name in routed_to:
            agent = AGENTS[agent_name]
            try:
                result = agent.run(user_message, context=session_context)
                responses.append(result)
            except Exception as exc:
                logger.exception("Agent %s failed: %s", agent_name, exc)
                responses.append({"agent": agent_name, "result": None, "error": str(exc)})

        # Build a combined summary if multiple agents were invoked
        if len(responses) == 1:
            summary = responses[0].get("result", "")
        else:
            parts = [f"[{r['agent'].upper()}] {r.get('result', r.get('error', ''))}" for r in responses]
            summary = "\n\n".join(parts)

        return {
            "routed_to": routed_to,
            "responses": responses,
            "summary": summary,
        }
