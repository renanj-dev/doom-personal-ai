"""Doom Tool Engine v1.4.

A small, dependency-light tool registry with explicit permission classes,
argument validation, confirmation tokens and append-only audit events.
This module intentionally does NOT execute arbitrary shell commands.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import ast
import math
import operator
import platform
import secrets
from typing import Any, Callable


class Permission:
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    permission: str
    handler: Callable[..., Any]
    parameters: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    tool: str
    data: Any = None
    error: str | None = None
    permission: str | None = None
    confirmation_token: str | None = None


@dataclass(frozen=True)
class AuditEvent:
    timestamp: str
    tool: str
    action: str
    permission: str
    ok: bool
    session_id: str
    detail: str = ""


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _safe_number(value: str) -> float:
    try:
        return float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("valor numérico inválido") from exc


# ---- Safe calculator -----------------------------------------------------
_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARYOPS = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}
_ALLOWED_FUNCS = {
    "sqrt": math.sqrt,
    "abs": abs,
    "round": round,
    "sin": math.sin,
    "cos": math.cos,
    "tan": math.tan,
    "log": math.log,
    "log10": math.log10,
}
_ALLOWED_NAMES = {"pi": math.pi, "e": math.e}


def _eval_math(node: ast.AST) -> float:
    if isinstance(node, ast.Expression):
        return _eval_math(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        left, right = _eval_math(node.left), _eval_math(node.right)
        return _ALLOWED_BINOPS[type(node.op)](left, right)
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARYOPS:
        return _ALLOWED_UNARYOPS[type(node.op)](_eval_math(node.operand))
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        if node.keywords:
            raise ValueError("argumentos nomeados não são permitidos")
        return _ALLOWED_FUNCS[node.func.id](*[_eval_math(arg) for arg in node.args])
    raise ValueError("expressão contém uma operação não permitida")


def calculator(expression: str) -> dict[str, Any]:
    expression = (expression or "").strip()
    if not expression or len(expression) > 200:
        raise ValueError("expressão vazia ou longa demais")
    tree = ast.parse(expression, mode="eval")
    value = _eval_math(tree)
    if not math.isfinite(value):
        raise ValueError("resultado não finito")
    return {"expression": expression, "result": value}


def current_time() -> dict[str, str]:
    return {"utc": utc_now().isoformat()}


def system_info() -> dict[str, str]:
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


class ToolEngine:
    def __init__(self) -> None:
        self._tools: dict[str, ToolSpec] = {}
        self._pending: dict[str, tuple[str, str, dict[str, Any], str]] = {}
        self.audit_log: list[AuditEvent] = []

    def register(self, spec: ToolSpec) -> None:
        if spec.permission not in {Permission.SAFE, Permission.CONFIRM, Permission.BLOCKED}:
            raise ValueError(f"permissão inválida: {spec.permission}")
        if spec.name in self._tools:
            raise ValueError(f"ferramenta já registrada: {spec.name}")
        self._tools[spec.name] = spec

    def list_tools(self) -> list[dict[str, Any]]:
        return [
            {
                "name": s.name,
                "description": s.description,
                "permission": s.permission,
                "parameters": s.parameters,
            }
            for s in self._tools.values()
        ]

    def _audit(self, tool: str, action: str, permission: str, ok: bool, session_id: str, detail: str = "") -> None:
        self.audit_log.append(
            AuditEvent(
                timestamp=utc_now().isoformat(),
                tool=tool,
                action=action,
                permission=permission,
                ok=ok,
                session_id=session_id,
                detail=detail,
            )
        )

    def invoke(self, name: str, args: dict[str, Any] | None = None, *, session_id: str = "main", confirmation_token: str | None = None) -> ToolResult:
        args = args or {}
        spec = self._tools.get(name)
        if not spec:
            self._audit(name, "invoke", "unknown", False, session_id, "tool not found")
            return ToolResult(False, name, error="Ferramenta não encontrada.")

        if spec.permission == Permission.BLOCKED:
            self._audit(name, "blocked", spec.permission, False, session_id, "blocked by policy")
            return ToolResult(False, name, error="Esta ferramenta está bloqueada pela política da Doom.", permission=spec.permission)

        if spec.permission == Permission.CONFIRM:
            if not confirmation_token or self._pending.get(confirmation_token) != (session_id, name, args, spec.permission):
                token = secrets.token_urlsafe(18)
                self._pending[token] = (session_id, name, args, spec.permission)
                self._audit(name, "confirmation_requested", spec.permission, True, session_id)
                return ToolResult(False, name, error="Confirmação necessária.", permission=spec.permission, confirmation_token=token)
            self._pending.pop(confirmation_token, None)

        try:
            data = spec.handler(**args)
        except Exception as exc:
            self._audit(name, "invoke", spec.permission, False, session_id, str(exc))
            return ToolResult(False, name, error=str(exc), permission=spec.permission)

        self._audit(name, "invoke", spec.permission, True, session_id)
        return ToolResult(True, name, data=data, permission=spec.permission)


def build_default_engine() -> ToolEngine:
    engine = ToolEngine()
    engine.register(ToolSpec(
        name="calculator",
        description="Calcula expressões matemáticas sem executar código arbitrário.",
        permission=Permission.SAFE,
        handler=calculator,
        parameters={"expression": "string"},
    ))
    engine.register(ToolSpec(
        name="current_time",
        description="Retorna o horário UTC do servidor.",
        permission=Permission.SAFE,
        handler=current_time,
    ))
    engine.register(ToolSpec(
        name="system_info",
        description="Retorna informações básicas não sensíveis do ambiente que executa a Doom.",
        permission=Permission.SAFE,
        handler=system_info,
    ))
    # Reserved by design: the next stages can register high-impact tools only
    # after defining explicit sandboxing and confirmation behavior.
    return engine
