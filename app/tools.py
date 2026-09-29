from __future__ import annotations

import ast
import json
import math
import operator
import platform
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable

from .db import SessionLocal
from .models import ToolAuditRecord
from .security import PermissionEngine, PermissionMode

_ALLOWED_BINOPS = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.Pow: operator.pow,
    ast.Mod: operator.mod,
    ast.FloorDiv: operator.floordiv,
}
_ALLOWED_UNARY = {ast.UAdd: operator.pos, ast.USub: operator.neg}
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


def _eval(node: ast.AST):
    if isinstance(node, ast.Expression):
        return _eval(node.body)
    if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
        return node.value
    if isinstance(node, ast.BinOp) and type(node.op) in _ALLOWED_BINOPS:
        return _ALLOWED_BINOPS[type(node.op)](_eval(node.left), _eval(node.right))
    if isinstance(node, ast.UnaryOp) and type(node.op) in _ALLOWED_UNARY:
        return _ALLOWED_UNARY[type(node.op)](_eval(node.operand))
    if isinstance(node, ast.Name) and node.id in _ALLOWED_NAMES:
        return _ALLOWED_NAMES[node.id]
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id in _ALLOWED_FUNCS:
        if node.keywords:
            raise ValueError("argumentos nomeados não são permitidos")
        return _ALLOWED_FUNCS[node.func.id](*[_eval(a) for a in node.args])
    raise ValueError("expressão contém uma operação não permitida")


def calculator(expression: str):
    if not expression or len(expression) > 200:
        raise ValueError("expressão vazia ou longa demais")
    value = _eval(ast.parse(expression.strip(), mode="eval"))
    if not math.isfinite(value):
        raise ValueError("resultado não finito")
    return {"expression": expression.strip(), "result": value}


def current_time():
    from datetime import datetime, timezone

    return {"utc": datetime.now(timezone.utc).isoformat()}


def system_info():
    return {
        "system": platform.system(),
        "release": platform.release(),
        "machine": platform.machine(),
        "python": platform.python_version(),
    }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    handler: Callable[..., Any]
    default_mode: str
    parameters: dict[str, dict[str, Any]]
    category: str = "core"
    version: str = "2.0"
    timeout_seconds: float = 8.0
    retries: int = 1


class ToolEngine:
    REQUEST_PREFIX = "DOOM_TOOL_REQUEST"
    MAX_BATCH = 5

    def __init__(self):
        self.tools: dict[str, ToolSpec] = {}
        self.register(
            ToolSpec(
                "calculator",
                "Calcula expressões matemáticas com um parser seguro.",
                calculator,
                PermissionMode.SAFE,
                {"expression": {"type": "string", "required": True, "max_length": 200}},
                category="math",
            )
        )
        self.register(
            ToolSpec(
                "current_time",
                "Retorna o horário UTC do servidor.",
                current_time,
                PermissionMode.SAFE,
                {},
                category="system",
            )
        )
        self.register(
            ToolSpec(
                "system_info",
                "Retorna informações básicas do ambiente do servidor.",
                system_info,
                PermissionMode.SAFE,
                {},
                category="system",
            )
        )

    def register(self, spec: ToolSpec):
        self.tools[spec.name] = spec

    def catalog(self):
        return [
            {
                "name": spec.name,
                "description": spec.description,
                "permission": spec.default_mode,
                "parameters": spec.parameters,
                "category": spec.category,
                "version": spec.version,
                "timeout_seconds": spec.timeout_seconds,
                "retries": spec.retries,
            }
            for spec in self.tools.values()
        ]

    def parse_request(self, text: str):
        text = (text or "").strip()
        if not text:
            return None
        if text.startswith(self.REQUEST_PREFIX):
            text = text[len(self.REQUEST_PREFIX) :].strip()
        if text.startswith("```json") and text.endswith("```"):
            text = text[7:-3].strip()
        try:
            payload = json.loads(text)
        except Exception:
            return None
        if (
            not isinstance(payload, dict)
            or set(payload) != {"tool", "args"}
            or not isinstance(payload.get("tool"), str)
            or not isinstance(payload.get("args"), dict)
        ):
            return None
        tool_name = payload["tool"].strip()
        if tool_name not in self.tools:
            return {"tool": tool_name, "args": payload["args"], "invalid": True}
        return {"tool": tool_name, "args": payload["args"], "invalid": False}

    @staticmethod
    def _type_matches(value: Any, expected: str) -> bool:
        return {
            "string": isinstance(value, str),
            "number": isinstance(value, (int, float)) and not isinstance(value, bool),
            "integer": isinstance(value, int) and not isinstance(value, bool),
            "boolean": isinstance(value, bool),
            "object": isinstance(value, dict),
            "array": isinstance(value, list),
        }.get(expected, False)

    def validate_args(self, spec: ToolSpec, args: dict[str, Any]) -> dict[str, Any]:
        if not isinstance(args, dict):
            return {"ok": False, "error": "Os argumentos da ferramenta precisam ser um objeto JSON."}

        unknown = sorted(set(args) - set(spec.parameters))
        if unknown:
            return {"ok": False, "error": f"Parâmetros não permitidos: {', '.join(unknown)}."}

        for name, rule in spec.parameters.items():
            required = bool(rule.get("required", False))
            if required and name not in args:
                return {"ok": False, "error": f"Parâmetro obrigatório ausente: {name}."}
            if name not in args:
                continue
            value = args[name]
            expected = str(rule.get("type", ""))
            if expected and not self._type_matches(value, expected):
                return {"ok": False, "error": f"Tipo inválido para {name}: esperado {expected}."}
            if isinstance(value, str) and "max_length" in rule and len(value) > int(rule["max_length"]):
                return {"ok": False, "error": f"Parâmetro {name} excede o limite permitido."}

        return {"ok": True, "args": args}

    def execute(
        self,
        name: str,
        args: dict[str, Any],
        session_id: str,
        user_id: str | None = None,
        confirmation_token: str | None = None,
    ):
        request_id = uuid.uuid4().hex
        started = time.perf_counter()
        spec = self.tools.get(name)
        if not spec:
            self._audit(session_id, name, "not_found", PermissionMode.BLOCKED, False, "tool_not_found", request_id)
            return self._result(request_id, name, "not_found", False, started, error="Ferramenta não encontrada.")

        validation = self.validate_args(spec, args)
        if not validation["ok"]:
            self._audit(session_id, name, "validate", "validation", False, validation["error"], request_id)
            return self._result(request_id, name, "invalid_args", False, started, error=validation["error"])

        pe = PermissionEngine()
        decision = pe.authorize(name, session_id, user_id, args, spec.default_mode, confirmation_token)
        self._audit(session_id, name, "authorize", decision["mode"], bool(decision["allowed"]), decision["reason"], request_id)

        if not decision["allowed"]:
            result = self._result(
                request_id,
                name,
                "confirmation_required" if decision.get("requires_confirmation") else "blocked",
                False,
                started,
                error="A ferramenta exige confirmação antes da execução." if decision.get("requires_confirmation") else "A execução foi bloqueada pela política da Doom.",
            )
            if decision.get("requires_confirmation"):
                result.update(
                    {
                        "requires_confirmation": True,
                        "confirmation_token": decision.get("confirmation_token"),
                        "expires_in": decision.get("expires_in", 120),
                        "args": args,
                    }
                )
            return result

        from .config import get_settings
        runtime = get_settings()
        max_attempts = max(1, min(spec.retries + 1, runtime.tool_max_retries + 1, 3))
        timeout_seconds = max(0.1, float(min(spec.timeout_seconds, runtime.tool_timeout_seconds)))
        last_error = ""
        for attempt in range(1, max_attempts + 1):
            try:
                with ThreadPoolExecutor(max_workers=1, thread_name_prefix="doom-tool") as executor:
                    future = executor.submit(spec.handler, **args)
                    data = future.result(timeout=timeout_seconds)
                self._audit(
                    session_id,
                    name,
                    "execute",
                    decision["mode"],
                    True,
                    f"attempt={attempt}",
                    request_id,
                )
                return self._result(request_id, name, "executed", True, started, data=data, attempt=attempt)
            except FutureTimeoutError:
                last_error = f"Tempo limite de {timeout_seconds:.1f}s excedido."
                self._audit(session_id, name, "timeout", decision["mode"], False, last_error, request_id)
            except Exception as exc:
                last_error = str(exc)[:1000]
                if attempt < max_attempts:
                    self._audit(session_id, name, "retry", decision["mode"], False, f"attempt={attempt}", request_id)
                    continue
                self._audit(session_id, name, "execute", decision["mode"], False, last_error, request_id)

        return self._result(request_id, name, "error", False, started, error=last_error or "Falha desconhecida.", attempt=max_attempts)

    def execute_many(
        self,
        calls: list[dict[str, Any]],
        session_id: str,
        user_id: str | None = None,
    ) -> dict[str, Any]:
        if not isinstance(calls, list) or not calls:
            return {"ok": False, "status": "invalid_batch", "error": "Nenhuma chamada de ferramenta foi informada."}
        from .config import get_settings
        max_batch = max(1, min(get_settings().tool_max_batch, self.MAX_BATCH))
        if len(calls) > max_batch:
            return {"ok": False, "status": "invalid_batch", "error": f"O lote excede o limite de {max_batch} ferramentas."}

        results = []
        for call in calls:
            if not isinstance(call, dict) or not isinstance(call.get("tool"), str) or not isinstance(call.get("args", {}), dict):
                return {"ok": False, "status": "invalid_batch", "results": results, "error": "Cada chamada precisa conter tool e args."}
            result = self.execute(call["tool"], call.get("args", {}), session_id, user_id, call.get("confirmation_token"))
            results.append(result)
            if result.get("requires_confirmation") or not result.get("ok"):
                return {"ok": False, "status": result.get("status", "error"), "results": results}
        return {"ok": True, "status": "executed", "results": results}

    @staticmethod
    def _result(request_id, name, status, ok, started, data=None, error=None, attempt=None):
        result = {
            "ok": ok,
            "status": status,
            "tool": name,
            "request_id": request_id,
            "duration_ms": int((time.perf_counter() - started) * 1000),
        }
        if attempt is not None:
            result["attempt"] = attempt
        if data is not None:
            result["data"] = data
        if error:
            result["error"] = error
        return result

    @staticmethod
    def _audit(session_id, tool, action, permission, ok, detail, request_id):
        try:
            with SessionLocal() as db:
                safe_detail = str(detail or "")[:2000]
                db.add(
                    ToolAuditRecord(
                        session_id=session_id,
                        tool=tool,
                        action=action,
                        permission=permission,
                        ok=ok,
                        detail=f"request_id={request_id} {safe_detail}".strip(),
                    )
                )
                db.commit()
        except Exception:
            pass


TOOL_ENGINE = ToolEngine()
