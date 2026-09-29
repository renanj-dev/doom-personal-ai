"""Doom v1.4.4 - History & Memory Management Engine.

Adds explicit user-controlled deletion of conversation history and reliable editing
of persistent memories.  The service is intentionally independent from the main
FastAPI app so it can be integrated with the existing Doom v1.1/v1.2 data layer.

Design rules:
- deleting a conversation never deletes persistent memories;
- editing a memory updates the database first, then returns the saved record;
- edits validate content and category before committing;
- all mutating operations are transactional;
- sensitive message/memory content is not written to audit logs;
- security can be enforced through Doom v1.4.3's SecureToolGate.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any, Callable

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, create_engine, delete, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, relationship, sessionmaker


class Base(DeclarativeBase):
    pass


class MemoryCategory(StrEnum):
    IDENTITY = "identity"
    PREFERENCES = "preferences"
    EDUCATION = "education"
    WORK = "work"
    PROJECT = "project"
    TECHNOLOGY = "technology"
    GOALS = "goals"
    OTHER = "other"


class MutationStatus(StrEnum):
    OK = "ok"
    NOT_FOUND = "not_found"
    INVALID = "invalid"
    CONFLICT = "conflict"
    FORBIDDEN = "forbidden"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def normalize_dt(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


class Conversation(Base):
    __tablename__ = "conversations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    session_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    title: Mapped[str] = mapped_column(String(240), default="Nova conversa")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    messages: Mapped[list["Message"]] = relationship(
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    conversation_id: Mapped[int] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(32))
    content: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class Memory(Base):
    __tablename__ = "memories"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    category: Mapped[str] = mapped_column(String(64), default=MemoryCategory.OTHER.value, index=True)
    content: Mapped[str] = mapped_column(Text)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)


@dataclass(frozen=True)
class MutationResult:
    status: MutationStatus
    message: str
    data: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status is MutationStatus.OK


@dataclass(frozen=True)
class DeletionResult:
    status: MutationStatus
    session_id: str
    deleted_messages: int = 0
    deleted_conversation: bool = False
    deleted_pending_proposals: int = 0
    data: dict[str, Any] | None = None

    @property
    def ok(self) -> bool:
        return self.status is MutationStatus.OK


@dataclass(frozen=True)
class MemoryPatch:
    content: str | None = None
    category: str | None = None
    enabled: bool | None = None
    expected_revision: int | None = None


def validate_memory_patch(patch: MemoryPatch) -> str | None:
    if patch.content is not None:
        if not patch.content.strip():
            return "memory_content_cannot_be_blank"
        if len(patch.content.strip()) > 4000:
            return "memory_content_too_long"
    if patch.category is not None:
        try:
            MemoryCategory(patch.category)
        except ValueError:
            return "invalid_memory_category"
    if patch.expected_revision is not None and patch.expected_revision < 1:
        return "invalid_expected_revision"
    if patch.content is None and patch.category is None and patch.enabled is None:
        return "empty_memory_patch"
    return None


class MemoryHistoryStore:
    """Persistence layer for the v1.4.4 feature.

    The canonical schema mirrors the structures used by Doom's conversation and
    persistent-memory layers.  Existing Doom deployments can reuse the service
    methods with their own ORM models by following the integration examples.
    """

    def __init__(self, database_url: str):
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def close(self) -> None:
        self.engine.dispose()

    def get_conversation(self, session_id: str) -> Conversation | None:
        with self.SessionLocal() as db:
            return db.scalar(select(Conversation).where(Conversation.session_id == session_id))

    def list_conversations(self, *, limit: int = 100) -> list[Conversation]:
        with self.SessionLocal() as db:
            stmt = select(Conversation).order_by(Conversation.updated_at.desc()).limit(limit)
            return list(db.scalars(stmt).all())

    def delete_conversation(self, session_id: str) -> DeletionResult:
        with self.SessionLocal() as db:
            conversation = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
            if conversation is None:
                return DeletionResult(MutationStatus.NOT_FOUND, session_id)

            message_count = len(conversation.messages)
            db.delete(conversation)
            db.commit()
            return DeletionResult(
                status=MutationStatus.OK,
                session_id=session_id,
                deleted_messages=message_count,
                deleted_conversation=True,
            )

    def get_memory(self, memory_id: int, *, user_id: str | None = None) -> Memory | None:
        with self.SessionLocal() as db:
            row = db.get(Memory, memory_id)
            if row is None:
                return None
            if user_id is not None and row.user_id not in (None, user_id):
                return None
            return row

    def list_memories(self, *, user_id: str | None = None, include_disabled: bool = True, limit: int = 500) -> list[Memory]:
        with self.SessionLocal() as db:
            stmt = select(Memory)
            if user_id is not None:
                stmt = stmt.where(Memory.user_id == user_id)
            if not include_disabled:
                stmt = stmt.where(Memory.enabled.is_(True))
            stmt = stmt.order_by(Memory.updated_at.desc()).limit(limit)
            return list(db.scalars(stmt).all())

    def update_memory(self, memory_id: int, patch: MemoryPatch, *, user_id: str | None = None) -> MutationResult:
        error = validate_memory_patch(patch)
        if error:
            return MutationResult(MutationStatus.INVALID, error)

        with self.SessionLocal() as db:
            row = db.get(Memory, memory_id)
            if row is None:
                return MutationResult(MutationStatus.NOT_FOUND, "memory_not_found")
            if user_id is not None and row.user_id not in (None, user_id):
                return MutationResult(MutationStatus.FORBIDDEN, "memory_belongs_to_another_user")
            if patch.expected_revision is not None and row.revision != patch.expected_revision:
                return MutationResult(
                    MutationStatus.CONFLICT,
                    "memory_revision_conflict",
                    {"current_revision": row.revision},
                )

            if patch.content is not None:
                row.content = patch.content.strip()
            if patch.category is not None:
                row.category = MemoryCategory(patch.category).value
            if patch.enabled is not None:
                row.enabled = patch.enabled
            row.revision += 1
            row.updated_at = utc_now()
            db.commit()
            db.refresh(row)
            return MutationResult(MutationStatus.OK, "memory_updated", memory_to_dict(row))

    def delete_memory(self, memory_id: int, *, user_id: str | None = None) -> MutationResult:
        with self.SessionLocal() as db:
            row = db.get(Memory, memory_id)
            if row is None:
                return MutationResult(MutationStatus.NOT_FOUND, "memory_not_found")
            if user_id is not None and row.user_id not in (None, user_id):
                return MutationResult(MutationStatus.FORBIDDEN, "memory_belongs_to_another_user")
            db.delete(row)
            db.commit()
            return MutationResult(MutationStatus.OK, "memory_deleted", {"memory_id": memory_id})


def memory_to_dict(row: Memory) -> dict[str, Any]:
    return {
        "id": row.id,
        "user_id": row.user_id,
        "category": row.category,
        "content": row.content,
        "enabled": row.enabled,
        "revision": row.revision,
        "created_at": normalize_dt(row.created_at).isoformat() if row.created_at else None,
        "updated_at": normalize_dt(row.updated_at).isoformat() if row.updated_at else None,
    }


def conversation_to_dict(row: Conversation) -> dict[str, Any]:
    return {
        "id": row.id,
        "session_id": row.session_id,
        "title": row.title,
        "message_count": len(row.messages),
        "created_at": normalize_dt(row.created_at).isoformat() if row.created_at else None,
        "updated_at": normalize_dt(row.updated_at).isoformat() if row.updated_at else None,
    }


class MemoryHistoryService:
    """Business layer with optional v1.4.3 security and v1.4.2 audit hooks."""

    def __init__(
        self,
        store: MemoryHistoryStore,
        *,
        authorize: Callable[..., dict[str, Any]] | None = None,
        audit: Callable[..., Any] | None = None,
    ):
        self.store = store
        self.authorize = authorize
        self.audit = audit

    def _guard(
        self,
        *,
        action_tool: str,
        session_id: str,
        user_id: str | None,
        args: dict[str, Any],
        default_mode: str = "confirm",
        confirmation_token: str | None = None,
    ) -> MutationResult | None:
        if self.authorize is None:
            return None
        decision = self.authorize(
            tool_name=action_tool,
            session_id=session_id,
            user_id=user_id,
            args=args,
            default_mode=default_mode,
            confirmation_token=confirmation_token,
            issue_confirmation=confirmation_token is None,
        )
        if not decision.get("allowed"):
            status = MutationStatus.INVALID if decision.get("decision") == "confirm" else MutationStatus.FORBIDDEN
            return MutationResult(status, decision.get("reason", "action_not_authorized"), decision)
        return None

    def delete_history(
        self,
        *,
        session_id: str,
        user_id: str | None = None,
        confirmation_token: str | None = None,
    ) -> DeletionResult:
        guard = self._guard(
            action_tool="history_delete",
            session_id=session_id,
            user_id=user_id,
            args={"session_id": session_id},
            confirmation_token=confirmation_token,
        )
        if guard is not None:
            return DeletionResult(
                status=guard.status,
                session_id=session_id,
                data=guard.data,
            )

        result = self.store.delete_conversation(session_id)
        self._audit(session_id=session_id, tool="history_delete", action="delete_history", ok=result.ok, detail=result.status.value, metadata={
            "deleted_messages": result.deleted_messages,
        })
        return result

    def edit_memory(
        self,
        *,
        memory_id: int,
        session_id: str,
        patch: MemoryPatch,
        user_id: str | None = None,
        confirmation_token: str | None = None,
    ) -> MutationResult:
        content_hash = None
        if patch.content is not None:
            content_hash = hashlib.sha256(patch.content.strip().encode("utf-8")).hexdigest()
        args = {
            "memory_id": memory_id,
            "content_sha256": content_hash,
            "category": patch.category,
            "enabled": patch.enabled,
            "expected_revision": patch.expected_revision,
        }
        guard = self._guard(
            action_tool="memory_edit",
            session_id=session_id,
            user_id=user_id,
            args=args,
            confirmation_token=confirmation_token,
        )
        if guard is not None:
            return guard

        result = self.store.update_memory(memory_id, patch, user_id=user_id)
        self._audit(session_id=session_id, tool="memory_edit", action="edit_memory", ok=result.ok, detail=result.message, metadata={
            "memory_id": memory_id,
            "status": result.status.value,
            "revision": (result.data or {}).get("revision") if result.data else None,
        })
        return result

    def _audit(self, **kwargs: Any) -> None:
        if self.audit is None:
            return
        try:
            self.audit(**kwargs)
        except TypeError:
            # Keep the feature usable with a simple AuditSink(event) adapter.
            self.audit(kwargs)


__all__ = [
    "Base",
    "Conversation",
    "Message",
    "Memory",
    "MemoryCategory",
    "MemoryPatch",
    "MutationStatus",
    "MutationResult",
    "DeletionResult",
    "MemoryHistoryStore",
    "MemoryHistoryService",
    "memory_to_dict",
    "conversation_to_dict",
]
