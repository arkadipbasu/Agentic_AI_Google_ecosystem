"""
agents/base_agent.py
Abstract base for all sub-agents.
Agents use Vertex AI (Gemini) with function-calling to decide which
MCP tool to invoke, execute it, and return a structured result.
"""

import json
import logging
from abc import ABC, abstractmethod
from typing import Any

import vertexai
from vertexai.generative_models import (
    Content,
    FunctionDeclaration,
    GenerativeModel,
    Part,
    Tool,
)

from config import get_settings

logger = logging.getLogger(__name__)


class BaseAgent(ABC):
    """
    Base class for a single-domain agent.

    Subclasses set:
        name      — human-readable agent name
        system_prompt — the agent's role description
        tools_manifest — list of tool dicts with keys: name, description, parameters, fn
    """

    name: str = "base"
    system_prompt: str = "You are a helpful assistant."
    tools_manifest: list[dict[str, Any]] = []

    def __init__(self):
        settings = get_settings()
        vertexai.init(project=settings.GCP_PROJECT_ID, location=settings.GCP_REGION)
        self._model_name = settings.VERTEX_MODEL
        self._vertex_tools = self._build_vertex_tools()

    # ── Tool construction ─────────────────────────────────────────────────────

    def _build_vertex_tools(self) -> list[Tool]:
        declarations = []
        for t in self.tools_manifest:
            params = t.get("parameters", {})
            properties = {
                k: {"type": "string", "description": v}
                for k, v in params.items()
            }
            declarations.append(
                FunctionDeclaration(
                    name=t["name"],
                    description=t["description"],
                    parameters={
                        "type": "object",
                        "properties": properties,
                        "required": [],
                    },
                )
            )
        return [Tool(function_declarations=declarations)] if declarations else []

    def _resolve_tool(self, name: str):
        for t in self.tools_manifest:
            if t["name"] == name:
                return t["fn"]
        return None

    # ── Inference loop ────────────────────────────────────────────────────────

    def run(self, user_message: str, context: dict[str, Any] | None = None) -> dict[str, Any]:
        """
        Single-turn agent run.
        Returns {"agent": name, "result": ..., "tool_called": ..., "raw": ...}
        """
        model = GenerativeModel(
            self._model_name,
            system_instruction=self.system_prompt,
            tools=self._vertex_tools,
        )

        # Optionally inject prior context as a prior assistant turn
        history: list[Content] = []
        if context:
            history.append(
                Content(
                    role="user",
                    parts=[Part.from_text(f"Session context:\n{json.dumps(context)}")],
                )
            )
            history.append(
                Content(role="model", parts=[Part.from_text("Understood.")])
            )

        chat = model.start_chat(history=history)
        response = chat.send_message(user_message)

        tool_name = None
        tool_result = None

        # Handle function-call response
        candidate = response.candidates[0]
        for part in candidate.content.parts:
            if part.function_call:
                tool_name = part.function_call.name
                raw_args = dict(part.function_call.args)
                logger.info("Agent %s calling tool %s with args %s", self.name, tool_name, raw_args)

                fn = self._resolve_tool(tool_name)
                if fn is None:
                    tool_result = {"error": f"Tool {tool_name} not found"}
                else:
                    try:
                        tool_result = fn(**raw_args)
                    except Exception as exc:
                        logger.exception("Tool %s raised: %s", tool_name, exc)
                        tool_result = {"error": str(exc)}

                # Send result back to the model for a natural language summary
                function_response = Part.from_function_response(
                    name=tool_name, response={"content": tool_result}
                )
                final_response = chat.send_message(function_response)
                summary = final_response.text
                break
        else:
            # No function call — model answered directly
            summary = candidate.content.parts[0].text if candidate.content.parts else ""

        return {
            "agent": self.name,
            "result": summary,
            "tool_called": tool_name,
            "tool_output": tool_result,
        }

    @abstractmethod
    def describe(self) -> str:
        """One-line description for the orchestrator's routing prompt."""
        ...
