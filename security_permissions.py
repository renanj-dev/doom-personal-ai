"""Doom v1.4.3 - Security & Permissions Engine.

Persistent, deny-by-default-ish tool policy resolution with session/user overrides
and one-time, expiring confirmation tokens. This module is intentionally independent
from FastAPI, Cortex, and the concrete Tool Engine implementation.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum
import hashlib
import hmac
import json
import secrets
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer, String, Text, UniqueConstraint, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class PermissionMode(StrEnum):
    SAFE = "safe"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class PermissionScope(StrEnum):
    GLOBAL = "global"
    USER = "user"
    SESSION = "session"


class Decision(StrEnum):
    ALLOW = "allow"
    CONFIRM = "confirm"
    BLOCKED = "blocked"


class ConfirmationStatus(StrEnum):
    PENDING = "pending"
    USED = "used"
    REVOKED = "revoked"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def as_utc(value: datetime) -> datetime:
    """Normalize naive DB timestamps as UTC for SQLite compatibility."""
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _json_default(value: Any) -> Any:
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    return str(value)


def canonical_args(args: dict[str, Any] | None) -> str:
    return json.dumps(args or {}, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=_json_default)


def args_hash(args: dict[str, Any] | None) -> str:
    return hashlib.sha256(canonical_args(args).encode("utf-8")).hexdigest()


def hash_confirmation_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ToolPermission(Base):
    __tablename__ = "tool_permissions"
    __table_args__ = (
        UniqueConstraint("tool_name", "scope", "scope_id", name="uq_tool_permission_scope"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    scope: Mapped[str] = mapped_column(String(16), index=True)
    scope_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    mode: Mapped[str] = mapped_column(String(16), default=PermissionMode.BLOCKED.value)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)


class ToolConfirmation(Base):
    __tablename__ = "tool_confirmations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    tool_name: Mapped[str] = mapped_column(String(128), index=True)
    args_hash: Mapped[str] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


@dataclass(frozen=True)
class PermissionDecision:
    decision: Decision
    tool_name: str
    mode: PermissionMode
    source_scope: PermissionScope | None
    reason: str

    @property
    def allowed(self) -> bool:
        return self.decision is Decision.ALLOW

    @property
    def requires_confirmation(self) -> bool:
        return self.decision is Decision.CONFIRM


@dataclass(frozen=True)
class ConfirmationResult:
    ok: bool
    reason: str
    confirmation_id: int | None = None


class PermissionStore:
    """Persistence layer. Safe to point at Doom's existing DATABASE_URL."""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def upsert_permission(
        self,
        *,
        tool_name: str,
        scope: PermissionScope | str = PermissionScope.GLOBAL,
        scope_id: str | None = None,
        mode: PermissionMode | str = PermissionMode.BLOCKED,
        enabled: bool = True,
    ) -> ToolPermission:
        scope = PermissionScope(scope)
        mode = PermissionMode(mode)
        if scope is PermissionScope.GLOBAL:
            scope_id = None
        elif not scope_id:
            raise ValueError(f"scope_id is required for scope={scope.value}")

        now = utc_now()
        with self.SessionLocal() as db:
            stmt = select(ToolPermission).where(
                ToolPermission.tool_name == tool_name,
                ToolPermission.scope == scope.value,
                ToolPermission.scope_id == scope_id,
            )
            row = db.scalar(stmt)
            if row is None:
                row = ToolPermission(
                    tool_name=tool_name,
                    scope=scope.value,
                    scope_id=scope_id,
                    mode=mode.value,
                    enabled=enabled,
                    created_at=now,
                    updated_at=now,
                )
                db.add(row)
            else:
                row.mode = mode.value
                row.enabled = enabled
                row.updated_at = now
            db.commit()
            db.refresh(row)
            return row

    def find_permission(
        self,
        *,
        tool_name: str,
        scope: PermissionScope,
        scope_id: str | None,
    ) -> ToolPermission | None:
        with self.SessionLocal() as db:
            stmt = select(ToolPermission).where(
                ToolPermission.tool_name == tool_name,
                ToolPermission.scope == scope.value,
                ToolPermission.scope_id == scope_id,
            )
            return db.scalar(stmt)

    def create_confirmation(
        self,
        *,
        session_id: str,
        user_id: str | None,
        tool_name: str,
        args: dict[str, Any] | None,
        ttl_seconds: int = 120,
    ) -> tuple[str, ToolConfirmation]:
        if ttl_seconds <= 0 or ttl_seconds > 3600:
            raise ValueError("ttl_seconds must be between 1 and 3600")

        raw_token = secrets.token_urlsafe(32)
        now = utc_now()
        row = ToolConfirmation(
            token_hash=hash_confirmation_token(raw_token),
            session_id=session_id,
            user_id=user_id,
            tool_name=tool_name,
            args_hash=args_hash(args),
            created_at=now,
            expires_at=now + timedelta(seconds=ttl_seconds),
        )
        with self.SessionLocal() as db:
            db.add(row)
            db.commit()
            db.refresh(row)
        return raw_token, row

    def consume_confirmation(
        self,
        *,
        token: str,
        session_id: str,
        user_id: str | None,
        tool_name: str,
        args: dict[str, Any] | None,
    ) -> ConfirmationResult:
        token_digest = hash_confirmation_token(token)
        expected_args_hash = args_hash(args)
        now = utc_now()

        with self.SessionLocal() as db:
            row = db.scalar(select(ToolConfirmation).where(ToolConfirmation.token_hash == token_digest))
            if row is None:
                return ConfirmationResult(False, "invalid_confirmation")
            if row.revoked_at is not None:
                return ConfirmationResult(False, "confirmation_revoked", row.id)
            if row.used_at is not None:
                return ConfirmationResult(False, "confirmation_already_used", row.id)
            if as_utc(row.expires_at) <= now:
                return ConfirmationResult(False, "confirmation_expired", row.id)
            if row.session_id != session_id:
                return ConfirmationResult(False, "session_mismatch", row.id)
            if row.user_id != user_id:
                return ConfirmationResult(False, "user_mismatch", row.id)
            if row.tool_name != tool_name:
                return ConfirmationResult(False, "tool_mismatch", row.id)
            if not hmac.compare_digest(row.args_hash, expected_args_hash):
                return ConfirmationResult(False, "arguments_mismatch", row.id)

            row.used_at = now
            db.commit()
            return ConfirmationResult(True, "confirmed", row.id)

    def revoke_confirmation(self, confirmation_id: int) -> bool:
        with self.SessionLocal() as db:
            row = db.get(ToolConfirmation, confirmation_id)
            if row is None or row.used_at is not None or row.revoked_at is not None:
                return False
            row.revoked_at = utc_now()
            db.commit()
            return True

    def list_permissions(self, *, tool_name: str | None = None, limit: int = 200) -> list[ToolPermission]:
        with self.SessionLocal() as db:
            stmt = select(ToolPermission).order_by(ToolPermission.tool_name, ToolPermission.scope).limit(limit)
            if tool_name:
                stmt = stmt.where(ToolPermission.tool_name == tool_name)
            return list(db.scalars(stmt).all())


class PermissionEngine:
    """Resolves the effective permission before Tool Engine execution."""

    PRECEDENCE = (PermissionScope.SESSION, PermissionScope.USER, PermissionScope.GLOBAL)

    def __init__(self, store: PermissionStore):
        self.store = store

    def decide(
        self,
        *,
        tool_name: str,
        session_id: str,
        user_id: str | None = None,
        default_mode: PermissionMode | str = PermissionMode.BLOCKED,
    ) -> PermissionDecision:
        default_mode = PermissionMode(default_mode)

        candidates = (
            (PermissionScope.SESSION, session_id),
            (PermissionScope.USER, user_id),
            (PermissionScope.GLOBAL, None),
        )
        for scope, scope_id in candidates:
            if scope is PermissionScope.USER and not user_id:
                continue
            row = self.store.find_permission(tool_name=tool_name, scope=scope, scope_id=scope_id)
            if row is None:
                continue
            if not row.enabled:
                return PermissionDecision(
                    Decision.BLOCKED, tool_name, PermissionMode.BLOCKED, scope,
                    f"disabled_by_{scope.value}_policy",
                )
            mode = PermissionMode(row.mode)
            return self._decision_from_mode(tool_name, mode, scope)

        return self._decision_from_mode(tool_name, default_mode, None)

    @staticmethod
    def _decision_from_mode(tool_name: str, mode: PermissionMode, source: PermissionScope | None) -> PermissionDecision:
        decision = {
            PermissionMode.SAFE: Decision.ALLOW,
            PermissionMode.CONFIRM: Decision.CONFIRM,
            PermissionMode.BLOCKED: Decision.BLOCKED,
        }[mode]
        reason = f"mode_{mode.value}"
        return PermissionDecision(decision, tool_name, mode, source, reason)

    def issue_confirmation(
        self,
        *,
        decision: PermissionDecision,
        session_id: str,
        user_id: str | None,
        args: dict[str, Any] | None,
        ttl_seconds: int = 120,
    ) -> str:
        if not decision.requires_confirmation:
            raise ValueError("confirmation can only be issued for CONFIRM decisions")
        token, _ = self.store.create_confirmation(
            session_id=session_id,
            user_id=user_id,
            tool_name=decision.tool_name,
            args=args,
            ttl_seconds=ttl_seconds,
        )
        return token

    def confirm_and_authorize(
        self,
        *,
        tool_name: str,
        session_id: str,
        user_id: str | None,
        args: dict[str, Any] | None,
        confirmation_token: str | None,
        default_mode: PermissionMode | str = PermissionMode.BLOCKED,
    ) -> PermissionDecision:
        decision = self.decide(
            tool_name=tool_name,
            session_id=session_id,
            user_id=user_id,
            default_mode=default_mode,
        )
        if decision.decision is Decision.BLOCKED:
            return decision
        if decision.decision is Decision.ALLOW:
            return decision
        if not confirmation_token:
            return PermissionDecision(
                Decision.CONFIRM,
                tool_name,
                decision.mode,
                decision.source_scope,
                "confirmation_required",
            )
        result = self.store.consume_confirmation(
            token=confirmation_token,
            session_id=session_id,
            user_id=user_id,
            tool_name=tool_name,
            args=args,
        )
        if not result.ok:
            return PermissionDecision(
                Decision.BLOCKED,
                tool_name,
                decision.mode,
                decision.source_scope,
                result.reason,
            )
        return PermissionDecision(
            Decision.ALLOW,
            tool_name,
            decision.mode,
            decision.source_scope,
            "confirmation_consumed",
        )


class SecureToolGate:
    """Small adapter to put in front of an existing Tool Engine/bridge.

    It does not execute tools; it only authorizes an invocation and optionally
    issues a confirmation token. The caller should execute the tool only when
    the returned decision is ALLOW.
    """

    def __init__(self, permissions: PermissionEngine):
        self.permissions = permissions

    def authorize(
        self,
        *,
        tool_name: str,
        session_id: str,
        user_id: str | None,
        args: dict[str, Any] | None,
        default_mode: PermissionMode | str,
        confirmation_token: str | None = None,
        issue_confirmation: bool = False,
        confirmation_ttl_seconds: int = 120,
    ) -> dict[str, Any]:
        decision = self.permissions.confirm_and_authorize(
            tool_name=tool_name,
            session_id=session_id,
            user_id=user_id,
            args=args,
            confirmation_token=confirmation_token,
            default_mode=default_mode,
        )

        payload: dict[str, Any] = {
            "allowed": decision.allowed,
            "decision": decision.decision.value,
            "tool": decision.tool_name,
            "mode": decision.mode.value,
            "source_scope": decision.source_scope.value if decision.source_scope else "default",
            "reason": decision.reason,
        }

        if decision.requires_confirmation and issue_confirmation:
            payload["confirmation_token"] = self.permissions.issue_confirmation(
                decision=decision,
                session_id=session_id,
                user_id=user_id,
                args=args,
                ttl_seconds=confirmation_ttl_seconds,
            )
            payload["confirmation_expires_in"] = confirmation_ttl_seconds

        return payload
