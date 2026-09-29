"""Controlled Cortex <-> Tool Engine bridge for Doom v1.4.

The LLM can request a registered tool only through a strict JSON envelope.
The bridge validates the envelope, delegates execution to ToolEngine and
returns a structured result that can be fed back into the Cortex context.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
import re
from typing import Any, Callable

from .tool_engine import ToolEngine, ToolResult


@dataclass(frozen=True)
class ToolRequest:
    tool: str
    args: dict[str, Any]


@dataclass(frozen=True)
class BridgeResult:
    kind: str  # "text", "tool_result", "confirmation", "error"
    text: str = ""
    request: ToolRequest | None = None
    result: ToolResult | None = None


class CortexToolBridge:
    """Connects model output to ToolEngine without exposing execution APIs."""

    REQUEST_PREFIX = "DOOM_TOOL_REQUEST"

    def __init__(self, engine: ToolEngine, *, max_tool_rounds: int = 3) -> None:
        if max_tool_rounds < 1:
            raise ValueError("max_tool_rounds deve ser >= 1")
        self.engine = engine
        self.max_tool_rounds = max_tool_rounds

    def catalog(self) -> list[dict[str, Any]]:
        """Return the public tool catalog for the Cortex prompt."""
        return self.engine.list_tools()

    def build_system_addendum(self) -> str:
        catalog = self.catalog()
        lines = [
            "DOOM TOOL PROTOCOL:",
            "Use a tool only when necessary and only from the catalog below.",
            "To request a tool, output exactly one JSON object on one line:",
            '{"tool":"calculator","args":{"expression":"2+2"}}',
            "Do not wrap the JSON in Markdown. Do not invent tools or parameters.",
            "If no tool is needed, answer normally in natural language.",
            "CATALOG:",
        ]
        for item in catalog:
            lines.append(json.dumps(item, ensure_ascii=False, separators=(",", ":")))
        return "\n".join(lines)

    def parse_request(self, model_text: str) -> ToolRequest | None:
        """Parse only a complete JSON object representing a tool call.

        The parser intentionally avoids extracting arbitrary JSON from prose.
        This keeps the tool boundary predictable and auditable.
        """
        text = (model_text or "").strip()
        if not text or "{" not in text or "}" not in text:
            return None

        # Accept exactly one JSON object, optionally surrounded by whitespace.
        try:
            payload = json.loads(text)
        except json.JSONDecodeError:
            # Also accept a single fenced block as a small convenience for local testing.
            match = re.fullmatch(r"```json\s*(\{.*\})\s*```", text, flags=re.DOTALL | re.IGNORECASE)
            if not match:
                return None
            try:
                payload = json.loads(match.group(1))
            except json.JSONDecodeError:
                return None

        if not isinstance(payload, dict):
            return None
        if set(payload) != {"tool", "args"}:
            return None
        tool = payload.get("tool")
        args = payload.get("args")
        if not isinstance(tool, str) or not tool.strip():
            return None
        if not isinstance(args, dict):
            return None
        return ToolRequest(tool=tool.strip(), args=args)

    def handle_model_output(
        self,
        model_text: str,
        *,
        session_id: str,
        confirmation_token: str | None = None,
    ) -> BridgeResult:
        request = self.parse_request(model_text)
        if request is None:
            return BridgeResult(kind="text", text=model_text)

        result = self.engine.invoke(
            request.tool,
            request.args,
            session_id=session_id,
            confirmation_token=confirmation_token,
        )
        if result.confirmation_token:
            return BridgeResult(kind="confirmation", request=request, result=result)
        if not result.ok:
            return BridgeResult(kind="error", request=request, result=result)
        return BridgeResult(kind="tool_result", request=request, result=result)

    @staticmethod
    def format_tool_result(result: ToolResult) -> str:
        """Create a compact system-style message to re-enter the Cortex loop."""
        payload = {
            "tool": result.tool,
            "ok": result.ok,
            "data": result.data,
            "error": result.error,
        }
        return "DOOM_TOOL_RESULT\n" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))

    @staticmethod
    def format_confirmation(result: ToolResult, request: ToolRequest) -> str:
        return (
            f"A ferramenta '{request.tool}' requer confirmação explícita. "
            f"Token: {result.confirmation_token}. "
            f"Motivo: {result.error or 'confirmação necessária.'}"
        )

    def run_loop(
        self,
        *,
        user_message: str,
        session_id: str,
        ask_model: Callable[[str], str],
    ) -> tuple[str, list[BridgeResult]]:
        """Run a bounded Cortex/tool loop.

        ask_model receives a prompt/context string and returns model text.
        This adapter is intentionally independent of OpenRouter/Ollama/OpenAI.
        """
        prompt = user_message
        events: list[BridgeResult] = []

        for _ in range(self.max_tool_rounds + 1):
            model_text = ask_model(prompt)
            outcome = self.handle_model_output(model_text, session_id=session_id)
            events.append(outcome)

            if outcome.kind == "text":
                return outcome.text, events
            if outcome.kind == "confirmation":
                return self.format_confirmation(outcome.result, outcome.request), events  # type: ignore[arg-type]
            if outcome.kind == "error":
                return outcome.result.error or "A ferramenta não pôde ser executada.", events  # type: ignore[union-attr]

            prompt = (
                user_message
                + "\n\n"
                + self.format_tool_result(outcome.result)  # type: ignore[arg-type]
                + "\nResponda ao usuário usando o resultado."
            )

        return "Atingi o limite de execuções de ferramentas nesta solicitação.", events
