"""Doom Context Engine v1.8.2.

Builds a compact context bundle while keeping the current user request
strictly separate from historical/contextual material. Historical assistant
answers are not recalled across conversations because they are generated
content, not durable user facts.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable

from sqlalchemy import select
from sqlalchemy.orm import Session

from .models import Message
from .memory_engine import relevant_memories
from .user_profile import render_profile_for_query

STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
    "que", "para", "por", "em", "no", "na", "nos", "nas", "com", "sem", "sobre",
    "como", "eu", "me", "meu", "minha", "meus", "minhas", "você", "voce", "seu", "sua",
    "seus", "suas", "isso", "esse", "essa", "estes", "estas", "é", "e", "ser", "ter",
    "tem", "tenho", "mais", "muito", "muita", "também", "tambem", "já", "ja", "ainda",
}

GREETING_PATTERNS = (
    r"^bom dia(?:,? doom)?[!,. ]*$",
    r"^boa tarde(?:,? doom)?[!,. ]*$",
    r"^boa noite(?:,? doom)?[!,. ]*$",
    r"^ol[aá](?:,? doom)?[!,. ]*$",
    r"^oi(?:,? doom)?[!,. ]*$",
)
IDENTITY_PATTERNS = (
    "apresente-se", "se apresente", "quem é você", "quem e voce",
    "quem você é", "quem voce e", "fale sobre você", "fale sobre voce",
)
MEMORY_QUERY_PATTERNS = (
    "você lembra", "voce lembra", "doom lembra", "lembra de",
    "o que você lembra", "o que voce lembra", "qual é a sua memória",
    "qual e a sua memoria", "você se lembra", "voce se lembra",
)


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
    if q_clean and len(q_clean) >= 8 and q_clean in c_clean:
        phrase_bonus += 5.0
    role_bonus = 0.1 if role == "user" else 0.0
    return overlap * 2.0 + phrase_bonus + role_bonus


def _to_payload(message: Message) -> dict:
    return {"role": "assistant" if message.role == "assistant" else "user", "content": message.content}


def _is_greeting(query: str) -> bool:
    normalized = " ".join((query or "").strip().lower().split())
    return any(re.match(pattern, normalized, flags=re.IGNORECASE) for pattern in GREETING_PATTERNS)


def _is_identity_query(query: str) -> bool:
    normalized = " ".join((query or "").strip().lower().split())
    return any(pattern in normalized for pattern in IDENTITY_PATTERNS)


def _is_memory_query(query: str) -> bool:
    normalized = " ".join((query or "").strip().lower().split())
    return any(pattern in normalized for pattern in MEMORY_QUERY_PATTERNS)


def _recent_limit_for_query(query: str) -> int:
    # Greetings and identity questions should not be contaminated by old
    # topical turns. Memory questions also start from the current turn only
    # and recover prior user facts via explicit relevance recall.
    if _is_greeting(query) or _is_identity_query(query) or _is_memory_query(query):
        return 1
    return 6


def _select_recent(db: Session, session_id: str, query: str) -> list[Message]:
    limit = _recent_limit_for_query(query)
    stmt = select(Message).where(Message.session_id == session_id)
    # For greetings, identity questions and explicit memory questions, the
    # recent context must be a user turn, never an old assistant answer.
    if limit == 1:
        stmt = stmt.where(Message.role == "user")
    rows = list(db.scalars(stmt.order_by(Message.created_at.desc()).limit(limit)).all())
    rows.reverse()
    return rows


def _select_recalled(
    db: Session,
    session_id: str,
    query: str,
    recent: Iterable[Message],
    limit: int = 6,
) -> list[Message]:
    recent_ids = {m.id for m in recent}
    # Only recall the user's historical statements. Generated assistant
    # answers are deliberately excluded so an old response cannot become
    # an accidental instruction or substitute for the current request.
    stmt = select(Message).where(Message.role == "user")
    if recent_ids:
        stmt = stmt.where(Message.id.not_in(recent_ids))
    rows = list(db.scalars(stmt.order_by(Message.created_at.desc()).limit(500)).all())
    scored: list[tuple[float, Message]] = []
    for message in rows:
        score = _score(query, message.content, message.role)
        if message.session_id == session_id:
            score += 0.75
        # Require actual lexical relevance; never fill the bundle with the
        # newest unrelated messages.
        if score >= 2.1:
            scored.append((score, message))
    scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    selected: list[Message] = []
    seen_sessions: dict[str, int] = {}
    for _, message in scored:
        count = seen_sessions.get(message.session_id, 0)
        if count >= 2:
            continue
        selected.append(message)
        seen_sessions[message.session_id] = count + 1
        if len(selected) >= limit:
            break
    selected.sort(key=lambda message: message.created_at)
    return selected


def build_context(db: Session, session_id: str, query: str) -> ContextBundle:
    recent = _select_recent(db, session_id, query)
    recalled = _select_recalled(db, session_id, query, recent, limit=6)
    # Greetings and identity questions do not need durable memory retrieval;
    # this prevents generic mentions such as the assistant's own name from
    # pulling project memories into a simple conversational turn.
    memories = [] if (_is_greeting(query) or _is_identity_query(query)) else relevant_memories(db, query, limit=6)
    memory_text = "\n".join(f"[{m.category}] {m.content}" for m in memories)
    profile_text = render_profile_for_query(query)
    if _is_greeting(query) or _is_identity_query(query):
        strategy = "turno atual isolado + contexto durável mínimo"
    elif _is_memory_query(query):
        strategy = "turno atual isolado + lembranças do usuário relevantes + memórias relevantes"
    else:
        strategy = "até 6 mensagens recentes + até 6 lembranças do usuário relevantes + até 6 memórias relevantes"
    return ContextBundle(
        profile_text=profile_text,
        memory_text=memory_text,
        recent_messages=[_to_payload(m) for m in recent],
        recalled_messages=[_to_payload(m) for m in recalled],
        memory_count=len(memories),
        recent_count=len(recent),
        recalled_count=len(recalled),
        strategy=strategy,
    )
