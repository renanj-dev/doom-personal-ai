"""Persistent audit storage for Doom Tool Engine v1.4.2."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import DateTime, Integer, String, Text, create_engine, select
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


class Base(DeclarativeBase):
    pass


class ToolAuditRecord(Base):
    __tablename__ = "tool_audit_log"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    session_id: Mapped[str] = mapped_column(String(128), index=True)
    tool: Mapped[str] = mapped_column(String(128), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    permission: Mapped[str] = mapped_column(String(32), index=True)
    ok: Mapped[bool] = mapped_column(default=False, index=True)
    detail: Mapped[str] = mapped_column(Text, default="")
    metadata_json: Mapped[str] = mapped_column(Text, default="{}")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ToolAuditStore:
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = create_engine(database_url, pool_pre_ping=True)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False)

    def init(self) -> None:
        Base.metadata.create_all(self.engine)

    def record(self, *, timestamp: datetime | None = None, session_id: str, tool: str,
               action: str, permission: str, ok: bool, detail: str = "",
               metadata_json: str = "{}") -> int:
        with self.SessionLocal() as db:
            row = ToolAuditRecord(
                timestamp=timestamp or utc_now(),
                session_id=session_id,
                tool=tool,
                action=action,
                permission=permission,
                ok=ok,
                detail=detail,
                metadata_json=metadata_json,
            )
            db.add(row)
            db.commit()
            db.refresh(row)
            return row.id

    def recent(self, *, session_id: str | None = None, limit: int = 100) -> list[ToolAuditRecord]:
        with self.SessionLocal() as db:
            stmt = select(ToolAuditRecord).order_by(ToolAuditRecord.timestamp.desc()).limit(limit)
            if session_id:
                stmt = stmt.where(ToolAuditRecord.session_id == session_id)
            return list(db.scalars(stmt).all())


class AuditSink:
    """Small adapter that can be passed to a Tool Engine/bridge."""

    def __init__(self, store: ToolAuditStore):
        self.store = store

    def __call__(self, event: Any) -> int:
        return self.store.record(
            timestamp=getattr(event, "timestamp", None),
            session_id=getattr(event, "session_id", "main"),
            tool=getattr(event, "tool", "unknown"),
            action=getattr(event, "action", "unknown"),
            permission=getattr(event, "permission", "unknown"),
            ok=bool(getattr(event, "ok", False)),
            detail=getattr(event, "detail", ""),
        )
