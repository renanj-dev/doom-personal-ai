"""Doom Context Engine v1.3.

Builds a compact, relevant context bundle from:
- current conversation recency
- older/relevant messages from this and other conversations
- relevant persistent memories
- a focused user profile

This is intentionally deterministic and dependency-free for the first semantic
retrieval layer. A future version can replace the lexical scorer with embeddings
without changing the public contract.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Message, Memory
from .memory_engine import relevant_memories
from .user_profile import render_profile_for_query

STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
    "que", "para", "por", "em", "no", "na", "nos", "nas", "com", "sem", "sobre",
    "como", "eu", "me", "meu", "minha", "meus", "minhas", "você", "voce", "seu", "sua",
    "seus", "suas", "isso", "esse", "essa", "estes", "estas", "é", "e", "ser", "ter",
    "tem", "tenho", "mais", "muito", "muita", "também", "tambem", "já", "ja", "ainda",
}


@dataclass(frozen=True)
class ContextBundle:
    profile_text: str
    memory_text: str
    recent_messages: list[dict]
    recalled_messages: list[dict]
    memory_count: int
    recent_count: int
    recalled_count: int
    strategy: str


def _words(text: str) -> set[str]:
    normalized = re.sub(r"[^\wÀ-ÿ]+", " ", (text or "").lower(), flags=re.UNICODE)
    return {w for w in normalized.split() if len(w) >= 3 and w not in STOPWORDS}


def _score(query: str, content: str, role: str) -> float:
    q = _words(query)
    c = _words(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    phrase_bonus = 0.0
    q_clean = " ".join((query or "").lower().split())
    c_clean = " ".join((content or "").lower().split())
    if q_clean and q_clean in c_clean:
        phrase_bonus += 5.0
    role_bonus = 0.1 if role == "user" else 0.0
    return overlap * 2.0 + phrase_bonus + role_bonus


def _to_payload(message: Message) -> dict:
    return {"role": "assistant" if message.role == "assistant" else "user", "content": message.content}


def _select_recent(db: Session, session_id: str, limit: int = 12) -> list[Message]:
    rows = list(
        db.scalars(
            select(Message)
            .where(Message.session_id == session_id)
            .order_by(Message.created_at.desc())
            .limit(limit)
        ).all()
    )
    rows.reverse()
    return rows


def _select_recalled(db: Session, session_id: str, query: str, recent: Iterable[Message], limit: int = 8) -> list[Message]:
    recent_ids = {m.id for m in recent}
    stmt = select(Message)
    if recent_ids:
        stmt = stmt.where(Message.id.not_in(recent_ids))
    rows = list(db.scalars(stmt.order_by(Message.created_at.desc()).limit(300)).all())
    scored: list[tuple[float, Message]] = []
    for m in rows:
        # Prefer the current conversation slightly, then use older conversations
        # as cross-conversation recall.
        score = _score(query, m.content, m.role)
        if m.session_id == session_id:
            score += 1.25
        if score >= 2.1:
            scored.append((score, m))
    scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    selected: list[Message] = []
    seen_sessions: dict[str, int] = {}
    for score, m in scored:
        # Avoid flooding the context with one repeated message/session.
        count = seen_sessions.get(m.session_id, 0)
        if count >= 3:
            continue
        selected.append(m)
        seen_sessions[m.session_id] = count + 1
        if len(selected) >= limit:
            break
    selected.sort(key=lambda m: m.created_at)
    return selected


def build_context(db: Session, session_id: str, query: str) -> ContextBundle:
    recent = _select_recent(db, session_id, limit=12)
    recalled = _select_recalled(db, session_id, query, recent, limit=8)
    memories = relevant_memories(db, query, limit=8)
    memory_text = "\n".join(f"[{m.category}] {m.content}" for m in memories)
    profile_text = render_profile_for_query(query)
    return ContextBundle(
        profile_text=profile_text,
        memory_text=memory_text,
        recent_messages=[_to_payload(m) for m in recent],
        recalled_messages=[_to_payload(m) for m in recalled],
        memory_count=len(memories),
        recent_count=len(recent),
        recalled_count=len(recalled),
        strategy="12 recentes + até 8 lembranças relevantes + até 8 memórias + perfil focado",
    )
