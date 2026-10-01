"""Doom Knowledge Engine v1.10.

Knowledge is separate from Memory: it stores reference material such as study
notes, documents, formulas and technical content. Retrieval is relevance-based
and returns source metadata so the Cortex can distinguish knowledge from user
memory or conversation history.
"""
from __future__ import annotations

import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

from sqlalchemy import select, delete
from sqlalchemy.orm import Session

from .models import KnowledgeChunk, KnowledgeDocument

STOPWORDS = {
    "a", "o", "e", "de", "do", "da", "dos", "das", "um", "uma", "uns", "umas",
    "que", "para", "por", "em", "no", "na", "nos", "nas", "com", "sem", "sobre",
    "como", "eu", "me", "meu", "minha", "meus", "minhas", "você", "voce", "seu", "sua",
    "seus", "suas", "isso", "esse", "essa", "estes", "estas", "é", "e", "ser", "ter",
    "tem", "tenho", "mais", "muito", "muita", "também", "tambem", "já", "ja", "ainda",
    "não", "nao", "uma", "sobre", "qual", "quais", "dos", "das", "ao", "aos", "às", "as",
}

MAX_TEXT_CHARS = 2_000_000
CHUNK_SIZE = 1800
CHUNK_OVERLAP = 250


@dataclass(frozen=True)
class KnowledgeHit:
    document_id: int
    title: str
    source_name: str
    collection: str
    topic: str
    version: str
    source_uri: str
    chunk_index: int
    content: str
    score: float


def _words(text: str) -> set[str]:
    normalized = re.sub(r"[^\wÀ-ÿ]+", " ", (text or "").lower(), flags=re.UNICODE)
    return {w for w in normalized.split() if len(w) >= 3 and w not in STOPWORDS}


def _score(query: str, content: str) -> float:
    q = _words(query)
    c = _words(content)
    if not q or not c:
        return 0.0
    overlap = len(q & c)
    q_clean = " ".join((query or "").lower().split())
    c_clean = " ".join((content or "").lower().split())
    phrase_bonus = 4.0 if len(q_clean) >= 8 and q_clean in c_clean else 0.0
    return overlap * 2.0 + phrase_bonus


def _chunk_text(text: str) -> list[str]:
    clean = re.sub(r"\r\n?", "\n", text or "").strip()
    if not clean:
        return []
    if len(clean) <= CHUNK_SIZE:
        return [clean]
    chunks: list[str] = []
    start = 0
    while start < len(clean):
        end = min(len(clean), start + CHUNK_SIZE)
        if end < len(clean):
            split_at = max(clean.rfind("\n\n", start, end), clean.rfind(". ", start, end))
            if split_at > start + CHUNK_SIZE // 2:
                end = split_at + (2 if clean[split_at:split_at+2] == ". " else 0)
        piece = clean[start:end].strip()
        if piece:
            chunks.append(piece)
        if end >= len(clean):
            break
        start = max(0, end - CHUNK_OVERLAP)
    return chunks


def _extract_text(filename: str, data: bytes, mime_type: str = "") -> tuple[str, str]:
    suffix = Path(filename or "").suffix.lower()
    mime = (mime_type or "").lower()
    if suffix in {".txt", ".md", ".markdown", ".csv", ".json"} or mime.startswith("text/"):
        return data.decode("utf-8", errors="replace"), "text"
    if suffix == ".pdf" or mime == "application/pdf":
        from pypdf import PdfReader
        reader = PdfReader(io.BytesIO(data))
        text = "\n\n".join((page.extract_text() or "") for page in reader.pages)
        return text, "pdf"
    if suffix in {".docx"} or mime == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
        from docx import Document
        document = Document(io.BytesIO(data))
        paragraphs = [p.text for p in document.paragraphs if p.text.strip()]
        return "\n\n".join(paragraphs), "docx"
    raise ValueError("Formato não suportado. Use TXT, Markdown, PDF ou DOCX.")


class KnowledgeEngine:
    def create_text(
        self,
        db: Session,
        *,
        title: str,
        content: str,
        collection: str = "Geral",
        topic: str = "",
        version: str = "1",
        source_name: str = "texto manual",
        source_uri: str = "",
    ) -> KnowledgeDocument:
        return self._persist(
            db,
            title=title,
            content=content,
            collection=collection,
            topic=topic,
            version=version,
            source_name=source_name,
            source_uri=source_uri,
            source_type="text",
            mime_type="text/plain",
        )

    def ingest_file(
        self,
        db: Session,
        *,
        filename: str,
        data: bytes,
        mime_type: str = "",
        title: str | None = None,
        collection: str = "Geral",
        topic: str = "",
        version: str = "1",
        source_uri: str = "",
    ) -> KnowledgeDocument:
        if len(data) > 12 * 1024 * 1024:
            raise ValueError("Arquivo excede o limite de 12 MB.")
        text, source_type = _extract_text(filename, data, mime_type)
        return self._persist(
            db,
            title=(title or Path(filename).stem or "Documento").strip()[:220],
            content=text,
            collection=collection,
            topic=topic,
            version=version,
            source_name=filename[:260],
            source_uri=source_uri[:600],
            source_type=source_type,
            mime_type=(mime_type or "application/octet-stream")[:120],
        )

    def _persist(self, db: Session, **kwargs) -> KnowledgeDocument:
        content = re.sub(r"\n{3,}", "\n\n", (kwargs.get("content") or "").strip())
        if not content:
            raise ValueError("O conteúdo do conhecimento está vazio ou não pôde ser extraído.")
        if len(content) > MAX_TEXT_CHARS:
            raise ValueError("O conteúdo extraído excede o limite de 2 milhões de caracteres.")
        content_hash = hashlib.sha256(content.encode("utf-8")).hexdigest()
        existing = db.scalar(select(KnowledgeDocument).where(KnowledgeDocument.content_hash == content_hash))
        if existing:
            return existing
        doc = KnowledgeDocument(content=content, content_hash=content_hash, status="ready", **{k: v for k, v in kwargs.items() if k != "content"})
        db.add(doc)
        db.flush()
        for idx, chunk in enumerate(_chunk_text(content)):
            db.add(KnowledgeChunk(document_id=doc.id, chunk_index=idx, content=chunk))
        db.commit()
        db.refresh(doc)
        return doc

    def list_documents(self, db: Session, limit: int = 100) -> list[KnowledgeDocument]:
        return list(db.scalars(select(KnowledgeDocument).order_by(KnowledgeDocument.updated_at.desc()).limit(max(1, min(limit, 200)))).all())

    def get_document(self, db: Session, document_id: int) -> KnowledgeDocument | None:
        return db.get(KnowledgeDocument, document_id)

    def delete_document(self, db: Session, document_id: int) -> bool:
        doc = db.get(KnowledgeDocument, document_id)
        if not doc:
            return False
        db.execute(delete(KnowledgeChunk).where(KnowledgeChunk.document_id == document_id))
        db.delete(doc)
        db.commit()
        return True

    def search(self, db: Session, query: str, limit: int = 6) -> list[KnowledgeHit]:
        q = (query or "").strip()
        if len(_words(q)) < 1:
            return []
        rows = list(db.scalars(select(KnowledgeChunk).order_by(KnowledgeChunk.created_at.desc()).limit(1500)).all())
        doc_ids = {r.document_id for r in rows}
        docs = {d.id: d for d in db.scalars(select(KnowledgeDocument).where(KnowledgeDocument.id.in_(doc_ids))).all()} if doc_ids else {}
        scored: list[KnowledgeHit] = []
        for chunk in rows:
            doc = docs.get(chunk.document_id)
            if not doc or doc.status != "ready":
                continue
            score = _score(q, chunk.content)
            # Metadata relevance gives collection/topic useful weight without
            # letting a bare document label outrank the actual content.
            score += 1.25 * _score(q, " ".join([doc.title, doc.collection, doc.topic]))
            if score >= 2.0:
                scored.append(KnowledgeHit(doc.id, doc.title, doc.source_name, doc.collection, doc.topic, doc.version, doc.source_uri, chunk.chunk_index, chunk.content, score))
        scored.sort(key=lambda h: (h.score, h.document_id, h.chunk_index), reverse=True)
        return scored[:max(1, min(limit, 12))]

    def render_context(self, hits: Iterable[KnowledgeHit], max_chars: int = 18000) -> str:
        parts: list[str] = []
        total = 0
        for idx, hit in enumerate(hits, start=1):
            header = (
                f"[KNOWLEDGE {idx}] título={hit.title!r}; fonte={hit.source_name!r}; "
                f"coleção={hit.collection!r}; tópico={hit.topic!r}; versão={hit.version!r}; "
                f"documento_id={hit.document_id}; trecho={hit.chunk_index}"
            )
            piece = header + "\n" + hit.content.strip()
            if total + len(piece) > max_chars:
                break
            parts.append(piece)
            total += len(piece) + 2
        return "\n\n".join(parts)


KNOWLEDGE_ENGINE = KnowledgeEngine()
