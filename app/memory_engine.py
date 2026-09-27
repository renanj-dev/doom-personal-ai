from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from .models import Conversation, Message


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def new_session_id() -> str:
    return uuid4().hex


def make_title(text: str, limit: int = 56) -> str:
    clean = " ".join((text or "").strip().split())
    if not clean:
        return "Nova conversa"
    if len(clean) <= limit:
        return clean
    return clean[: limit - 1].rstrip() + "…"


def get_or_create_conversation(db: Session, session_id: str, first_message: str | None = None) -> Conversation:
    row = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    if row:
        return row
    row = Conversation(session_id=session_id, title=make_title(first_message or "Nova conversa"))
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def touch_conversation(db: Session, session_id: str, first_message: str | None = None) -> Conversation:
    row = get_or_create_conversation(db, session_id, first_message)
    row.updated_at = utcnow()
    if first_message and (row.title == "Nova conversa" or not row.title.strip()):
        row.title = make_title(first_message)
    db.commit()
    db.refresh(row)
    return row


def list_conversations(db: Session, include_archived: bool = False) -> list[Conversation]:
    stmt = select(Conversation).order_by(Conversation.updated_at.desc())
    if not include_archived:
        stmt = stmt.where(Conversation.archived.is_(False))
    return list(db.scalars(stmt).all())


def get_messages(db: Session, session_id: str, limit: int | None = None) -> list[Message]:
    stmt = select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
    if limit:
        rows = list(db.scalars(stmt.order_by(Message.created_at.desc()).limit(limit)).all())
        rows.reverse()
        return rows
    return list(db.scalars(stmt).all())


def search_history(db: Session, query: str, limit: int = 30) -> list[Message]:
    q = " ".join((query or "").strip().split())
    if not q:
        return []
    stmt = (
        select(Message)
        .where(Message.content.ilike(f"%{q}%"))
        .order_by(Message.created_at.desc())
        .limit(limit)
    )
    return list(db.scalars(stmt).all())


def delete_conversation(db: Session, session_id: str) -> bool:
    row = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
    db.query(Message).filter(Message.session_id == session_id).delete(synchronize_session=False)
    if row:
        db.delete(row)
    db.commit()
    return row is not None


def backfill_legacy_conversations(db: Session) -> int:
    """Create conversation rows for messages created before Memory Engine v1.1."""
    session_ids = list(db.scalars(select(Message.session_id).distinct()).all())
    created = 0
    for session_id in session_ids:
        exists = db.scalar(select(Conversation).where(Conversation.session_id == session_id))
        if exists:
            continue
        first_user = db.scalar(
            select(Message).where(Message.session_id == session_id, Message.role == "user").order_by(Message.created_at.asc())
        )
        first_any = db.scalar(
            select(Message).where(Message.session_id == session_id).order_by(Message.created_at.asc())
        )
        seed = (first_user or first_any).content if (first_user or first_any) else "Nova conversa"
        row = Conversation(
            session_id=session_id,
            title=make_title(seed),
            created_at=(first_any.created_at if first_any else utcnow()),
            updated_at=(first_any.created_at if first_any else utcnow()),
        )
        db.add(row)
        created += 1
    if created:
        db.commit()
    return created
