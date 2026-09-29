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


# ---- Doom Memory Intelligence v1.2 ----
import re
from datetime import datetime, timezone
from sqlalchemy import desc
from .models import Memory, MemoryProposal

STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
    "que", "para", "por", "em", "no", "na", "nos", "nas", "com", "sem", "sobre",
    "como", "eu", "me", "meu", "minha", "meus", "minhas", "você", "voce", "seu", "sua",
    "seus", "suas", "isso", "esse", "essa", "estes", "estas", "é", "e", "ser", "ter",
    "tem", "tenho", "que", "mais", "muito", "muita", "uma", "também", "tambem",
}

MEMORY_TRIGGER_PATTERNS = (
    r"\blembre(?:-se)?\s+(?:que|disso)\b",
    r"\b(?:guarde|guardar|memorize|memorizar|registre|registrar)\s+(?:que|isso|esta informa[cç][aã]o)\b",
    r"\bquero que (?:voc[eê]|voce) (?:lembre|guarde|memorize|registre)\b",
    r"\bn[aã]o esque[cç]a\b",
)

AFFIRMATIVE_MEMORY = {"sim", "pode", "pode sim", "confirma", "confirmo", "sim, pode", "registre", "registra", "lembre", "isso"}
NEGATIVE_MEMORY = {"não", "nao", "não quero", "nao quero", "cancela", "cancelar", "esquece", "deixa"}

CATEGORY_KEYWORDS = {
    "projeto_doom": ("doom", "cortex", "memória da doom", "memoria da doom", "layout", "forest core", "app"),
    "educacao": ("estudo", "enem", "vestibular", "escola", "faculdade"),
    "aprendizado": ("aprendo", "aprender", "estudar", "explicação", "explicacao", "prefiro"),
    "tecnologia": ("computador", "pc", "python", "programação", "programacao", "ia", "inteligência artificial", "inteligencia artificial"),
    "trabalho": ("trabalho", "emprego", "vaga", "empresa"),
    "habilidades": ("habilidade", "sei fazer", "experiência", "experiencia"),
    "comunicacao": ("fale comigo", "responda", "tom", "linguagem", "comunicação", "comunicacao"),
}

def normalize_words(text: str) -> set[str]:
    words = re.findall(r"[\wÀ-ÿ]{3,}", (text or "").lower())
    return {w for w in words if w not in STOPWORDS}


def detect_memory_intent(message: str) -> bool:
    text = (message or "").strip().lower()
    return any(re.search(p, text) for p in MEMORY_TRIGGER_PATTERNS)


def extract_memory_content(message: str) -> str:
    text = " ".join((message or "").strip().split())
    patterns = [
        r"^(?:doom,?\s*)?(?:por favor,?\s*)?(?:lembre(?:-se)?|guarde|memorize|registre)\s+que\s+(.+)$",
        r"^(?:doom,?\s*)?(?:por favor,?\s*)?quero que (?:você|voce) (?:lembre|guarde|memorize|registre)\s+(.+)$",
        r"^(?:doom,?\s*)?(?:por favor,?\s*)?não esqueça(?: de)?\s+(.+)$",
    ]
    for pattern in patterns:
        m = re.match(pattern, text, flags=re.IGNORECASE)
        if m:
            return m.group(1).strip(" .")
    return text


def infer_memory_category(content: str) -> str:
    t = (content or "").lower()
    for category, keys in CATEGORY_KEYWORDS.items():
        if any(k in t for k in keys):
            return category
    return "general"


def create_memory_proposal(db: Session, session_id: str, content: str, category: str | None = None) -> MemoryProposal:
    proposal = MemoryProposal(
        session_id=session_id,
        category=category or infer_memory_category(content),
        content=content.strip(),
        status="pending",
    )
    db.add(proposal)
    db.commit()
    db.refresh(proposal)
    return proposal


def get_pending_proposal(db: Session, session_id: str) -> MemoryProposal | None:
    return db.scalar(
        select(MemoryProposal)
        .where(MemoryProposal.session_id == session_id, MemoryProposal.status == "pending")
        .order_by(desc(MemoryProposal.created_at))
        .limit(1)
    )


def resolve_memory_proposal(db: Session, proposal: MemoryProposal, approved: bool) -> Memory:
    proposal.status = "approved" if approved else "rejected"
    proposal.resolved_at = utcnow()
    if not approved:
        db.commit()
        raise ValueError("Memória recusada pelo usuário.")
    row = Memory(category=proposal.category, content=proposal.content, active=True)
    db.add(row)
    db.add(proposal)
    db.commit()
    db.refresh(row)
    return row


def cancel_memory_proposal(db: Session, proposal: MemoryProposal) -> None:
    proposal.status = "rejected"
    proposal.resolved_at = utcnow()
    db.commit()


def relevant_memories(db: Session, query: str, limit: int = 10) -> list[Memory]:
    memories = list(db.scalars(select(Memory).where(Memory.active.is_(True))).all())
    q_words = normalize_words(query)
    scored: list[tuple[float, Memory]] = []
    for memory in memories:
        m_words = normalize_words(memory.content)
        overlap = len(q_words & m_words)
        category_bonus = 0.0
        q = (query or "").lower()
        if memory.category == infer_memory_category(q) and memory.category != "general":
            category_bonus = 1.5
        recency_bonus = 0.1
        score = overlap * 2.0 + category_bonus + recency_bonus
        scored.append((score, memory))
    scored.sort(key=lambda item: (item[0], item[1].created_at), reverse=True)
    selected = [m for score, m in scored if score > 0][:limit]
    if len(selected) < min(limit, len(memories)):
        existing = {m.id for m in selected}
        newest = sorted(memories, key=lambda m: m.created_at, reverse=True)
        for m in newest:
            if m.id not in existing:
                selected.append(m)
                existing.add(m.id)
            if len(selected) >= limit:
                break
    return selected
