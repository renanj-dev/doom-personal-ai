from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import hmac
import json
import secrets

from sqlalchemy import select

from .db import SessionLocal
from .models import ToolConfirmation, ToolPermission


class PermissionMode:
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


VALID_MODES = {PermissionMode.SAFE, PermissionMode.CONFIRM, PermissionMode.BLOCKED}
VALID_SCOPES = {"global", "user", "session"}


@dataclass(frozen=True)
class Decision:
    allowed: bool
    requires_confirmation: bool
    mode: str
    source: str
    reason: str


def _hash_args(args: dict) -> str:
    return hashlib.sha256(
        json.dumps(args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    ).hexdigest()


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def get_effective_policy(tool: str, session_id: str, user_id: str | None, default_mode: str) -> dict:
    mode = default_mode
    enabled = True
    source = "default"
    scope = None
    scope_id = None
    with SessionLocal() as db:
        for candidate_scope, candidate_id in [("session", session_id), ("user", user_id), ("global", None)]:
            if candidate_scope == "user" and not user_id:
                continue
            row = db.scalar(
                select(ToolPermission).where(
                    ToolPermission.tool_name == tool,
                    ToolPermission.scope == candidate_scope,
                    ToolPermission.scope_id == candidate_id,
                )
            )
            if row:
                mode = PermissionMode.BLOCKED if not row.enabled else row.mode
                enabled = bool(row.enabled)
                source = candidate_scope
                scope = row.scope
                scope_id = row.scope_id
                break
    return {"mode": mode, "enabled": enabled, "source": source, "scope": scope, "scope_id": scope_id}


def upsert_permission(tool: str, scope: str, scope_id: str | None, mode: str, enabled: bool) -> ToolPermission:
    if scope not in VALID_SCOPES:
        raise ValueError("Escopo de permissão inválido.")
    if mode not in VALID_MODES:
        raise ValueError("Modo de permissão inválido.")
    if scope == "global":
        scope_id = None
    elif not scope_id:
        raise ValueError("scope_id é obrigatório para o escopo informado.")

    with SessionLocal() as db:
        row = db.scalar(
            select(ToolPermission).where(
                ToolPermission.tool_name == tool,
                ToolPermission.scope == scope,
                ToolPermission.scope_id == scope_id,
            )
        )
        now = datetime.now(timezone.utc)
        if row is None:
            row = ToolPermission(tool_name=tool, scope=scope, scope_id=scope_id, mode=mode, enabled=enabled)
            db.add(row)
        else:
            row.mode = mode
            row.enabled = enabled
            row.updated_at = now
        db.commit()
        db.refresh(row)
        return row


def delete_permission(tool: str, scope: str, scope_id: str | None) -> bool:
    if scope not in VALID_SCOPES:
        raise ValueError("Escopo de permissão inválido.")
    if scope == "global":
        scope_id = None
    with SessionLocal() as db:
        row = db.scalar(
            select(ToolPermission).where(
                ToolPermission.tool_name == tool,
                ToolPermission.scope == scope,
                ToolPermission.scope_id == scope_id,
            )
        )
        if not row:
            return False
        db.delete(row)
        db.commit()
        return True


class PermissionEngine:
    def authorize(
        self,
        tool: str,
        session_id: str,
        user_id: str | None,
        args: dict,
        default_mode: str,
        token: str | None = None,
    ):
        policy = get_effective_policy(tool, session_id, user_id, default_mode)
        mode = policy["mode"]
        source = policy["source"]

        with SessionLocal() as db:
            if mode == PermissionMode.BLOCKED:
                return {
                    "allowed": False,
                    "requires_confirmation": False,
                    "mode": mode,
                    "source": source,
                    "reason": "blocked_by_policy",
                }
            if mode == PermissionMode.SAFE:
                return {
                    "allowed": True,
                    "requires_confirmation": False,
                    "mode": mode,
                    "source": source,
                    "reason": "safe",
                }
            if not token:
                raw = secrets.token_urlsafe(32)
                now = datetime.now(timezone.utc)
                db.add(
                    ToolConfirmation(
                        token_hash=_hash_token(raw),
                        session_id=session_id,
                        user_id=user_id,
                        tool_name=tool,
                        args_hash=_hash_args(args),
                        created_at=now,
                        expires_at=now + timedelta(seconds=120),
                    )
                )
                db.commit()
                return {
                    "allowed": False,
                    "requires_confirmation": True,
                    "mode": mode,
                    "source": source,
                    "reason": "confirmation_required",
                    "confirmation_token": raw,
                    "expires_in": 120,
                }

            row = db.scalar(select(ToolConfirmation).where(ToolConfirmation.token_hash == _hash_token(token)))
            now = datetime.now(timezone.utc)
            if not row:
                return {"allowed": False, "requires_confirmation": False, "mode": mode, "source": source, "reason": "invalid_confirmation"}
            exp = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
            if row.used_at is not None:
                return {"allowed": False, "requires_confirmation": False, "mode": mode, "source": source, "reason": "confirmation_already_used"}
            if exp <= now:
                return {"allowed": False, "requires_confirmation": False, "mode": mode, "source": source, "reason": "confirmation_expired"}
            if row.session_id != session_id or row.user_id != user_id or row.tool_name != tool or not hmac.compare_digest(row.args_hash, _hash_args(args)):
                return {"allowed": False, "requires_confirmation": False, "mode": mode, "source": source, "reason": "confirmation_mismatch"}
            row.used_at = now
            db.commit()
            return {"allowed": True, "requires_confirmation": False, "mode": mode, "source": source, "reason": "confirmation_consumed"}
