"""Doom Safety & Legal Engine v1.8.

This module provides a conservative, deterministic policy layer for the Doom
prototype. It intentionally does not attempt to be a complete legal adviser.
It separates four outcomes:

- allow: ordinary request
- review: high-stakes topic; answer with caution
- break_glass: restricted/dual-use request needing an emergency grant
- blocked: hard safety boundary; never overridable

Break Glass is a bounded authorization mechanism, not a global safety bypass.
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from enum import StrEnum

from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .models import BreakGlassCredential, BreakGlassGrant, SafetyEvent

settings = get_settings()


class SafetyDecision(StrEnum):
    ALLOW = "allow"
    REVIEW = "review"
    BREAK_GLASS = "break_glass"
    BLOCKED = "blocked"


@dataclass(frozen=True)
class SafetyAssessment:
    decision: SafetyDecision
    category: str
    reason: str
    matched_rule: str | None = None


@dataclass(frozen=True)
class EmergencyAuthorization:
    token: str
    expires_at: datetime
    scope: str


_BLOCKED_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("harmful_instructions", re.compile(r"\b(fabricar|construir|montar|detonar|produzir)\b.*\b(bomba|explosivo|artefato explosivo)\b", re.I), "instruções perigosas e de fabricação de artefatos"),
    ("destructive_software", re.compile(r"\b(ransomware|malware destrutivo|apagar\s+dados|destruir\s+sistema)\b", re.I), "software destrutivo ou dano deliberado"),
    ("credential_theft", re.compile(r"\b(roubar|furtar|capturar)\b.*\b(senha|credencial|token de acesso)\b", re.I), "roubo de credenciais"),
    ("harm_evasion", re.compile(r"\b(esconder|ocultar)\b.*\b(evidências?|rastros?)\b.*\b(crime|ataque|invasão)\b", re.I), "ocultação de atividade maliciosa"),
]

_RESTRICTED_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("security_bypass", re.compile(r"\b(burlar|contornar|desativar|driblar)\b.*\b(segurança|autenticação|controle de acesso|firewall)\b", re.I), "pedido de contorno de controle de segurança"),
    ("unauthorized_access", re.compile(r"\b(invadi|invadir|explorar)\b.*\b(sistema|servidor|conta|rede)\b", re.I), "potencial acesso não autorizado"),
    ("evasion", re.compile(r"\b(escapar|evitar|driblar)\b.*\b(detecção|monitoramento|bloqueio)\b", re.I), "pedido de evasão de controles"),
]

_REVIEW_RULES: list[tuple[str, re.Pattern[str], str]] = [
    ("medical", re.compile(r"\b(diagnóstico|sintoma|doença|remédio|medicação|tratamento|dose|exame médico)\b", re.I), "tema médico de alto impacto"),
    ("legal", re.compile(r"\b(advogado|processo|contrato|lei|legal|jurídico|juridico|crime|multa|imposto)\b", re.I), "tema jurídico/regulatório"),
    ("financial", re.compile(r"\b(investimento|investir|ações|ação|renda fixa|imposto de renda|finanças|financeiro)\b", re.I), "tema financeiro"),
]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _pbkdf2(secret: str, salt: bytes, iterations: int = 240_000) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", secret.encode("utf-8"), salt, iterations, dklen=32)


def hash_secret(secret: str, salt: bytes | None = None, iterations: int = 240_000) -> tuple[str, str, int]:
    use_salt = salt or secrets.token_bytes(16)
    digest = _pbkdf2(secret, use_salt, iterations)
    return use_salt.hex(), digest.hex(), iterations


def verify_secret(secret: str, salt_hex: str, digest_hex: str, iterations: int) -> bool:
    try:
        candidate = _pbkdf2(secret, bytes.fromhex(salt_hex), iterations).hex()
        return hmac.compare_digest(candidate, digest_hex)
    except (ValueError, TypeError):
        return False


def generate_break_glass_key() -> str:
    return "DOOM-EG-" + secrets.token_urlsafe(32)


def generate_grant_token() -> str:
    return "doom-bg-" + secrets.token_urlsafe(32)


def assess_request(message: str) -> SafetyAssessment:
    if not settings.safety_enabled:
        return SafetyAssessment(SafetyDecision.ALLOW, "disabled", "Safety & Legal Engine desativado por configuração")
    text = (message or "").strip()
    if not text:
        return SafetyAssessment(SafetyDecision.ALLOW, "general", "mensagem vazia/irrelevante")

    for rule_id, pattern, reason in _BLOCKED_RULES:
        if pattern.search(text):
            return SafetyAssessment(SafetyDecision.BLOCKED, "hard_block", reason, rule_id)

    for rule_id, pattern, reason in _RESTRICTED_RULES:
        if pattern.search(text):
            return SafetyAssessment(SafetyDecision.BREAK_GLASS, "restricted", reason, rule_id)

    for rule_id, pattern, reason in _REVIEW_RULES:
        if pattern.search(text):
            return SafetyAssessment(SafetyDecision.REVIEW, "high_stakes", reason, rule_id)

    return SafetyAssessment(SafetyDecision.ALLOW, "general", "nenhuma regra especial acionada")


def _log_event(db: Session, *, event_type: str, session_id: str | None, decision: str | None, category: str | None, detail: str, grant_id: int | None = None) -> SafetyEvent:
    row = SafetyEvent(
        event_type=event_type,
        session_id=session_id,
        decision=decision,
        category=category,
        detail=detail[:2000],
        grant_id=grant_id,
    )
    db.add(row)
    return row


def _recent_failed_attempts(db: Session, session_id: str, minutes: int) -> int:
    cutoff = _utcnow() - timedelta(minutes=minutes)
    return len(db.scalars(
        select(SafetyEvent).where(
            SafetyEvent.event_type == "break_glass_auth_failed",
            SafetyEvent.session_id == session_id,
            SafetyEvent.created_at >= cutoff,
        )
    ).all())


def register_break_glass(db: Session, label: str = "Emergency Override") -> tuple[BreakGlassCredential, str]:
    key = generate_break_glass_key()
    salt_hex, digest_hex, iterations = hash_secret(key)
    row = BreakGlassCredential(
        label=(label or "Emergency Override").strip()[:120],
        key_salt=salt_hex,
        key_hash=digest_hex,
        hash_iterations=iterations,
        enabled=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    _log_event(db, event_type="break_glass_registered", session_id=None, decision="registered", category="break_glass", detail=f"credencial {row.id} registrada")
    db.commit()
    return row, key


def active_credentials(db: Session) -> list[BreakGlassCredential]:
    return list(db.scalars(select(BreakGlassCredential).where(BreakGlassCredential.enabled.is_(True)).order_by(BreakGlassCredential.created_at.desc())).all())


def authorize_break_glass(db: Session, *, session_id: str, key: str, reason: str, scope: str = "chat-restricted") -> EmergencyAuthorization:
    if not settings.emergency_break_glass_enabled:
        raise ValueError("Emergency Override está desativado na configuração do servidor.")
    if settings.emergency_require_reason and len((reason or "").strip()) < 5:
        raise ValueError("Informe um motivo com pelo menos 5 caracteres.")

    failures = _recent_failed_attempts(db, session_id, settings.emergency_cooldown_minutes)
    if failures >= settings.emergency_max_attempts:
        raise PermissionError("Limite de tentativas atingido. Tente novamente após o período de cooldown.")

    credential = None
    for candidate in active_credentials(db):
        if verify_secret(key or "", candidate.key_salt, candidate.key_hash, candidate.hash_iterations):
            credential = candidate
            break

    if credential is None:
        _log_event(db, event_type="break_glass_auth_failed", session_id=session_id, decision="denied", category="break_glass", detail="tentativa de chave inválida")
        db.commit()
        raise PermissionError("Chave Emergency Override inválida.")

    now = _utcnow()
    token = generate_grant_token()
    salt_hex, digest_hex, iterations = hash_secret(token)
    grant = BreakGlassGrant(
        credential_id=credential.id,
        session_id=session_id,
        scope=scope[:64],
        token_salt=salt_hex,
        token_hash=digest_hex,
        hash_iterations=iterations,
        reason=reason.strip()[:1000],
        issued_at=now,
        expires_at=now + timedelta(minutes=settings.emergency_session_minutes),
        used=False,
        revoked=False,
    )
    db.add(grant)
    credential.last_used_at = now
    db.flush()
    _log_event(db, event_type="break_glass_granted", session_id=session_id, decision="granted", category="break_glass", detail=reason, grant_id=grant.id)
    db.commit()
    return EmergencyAuthorization(token=token, expires_at=grant.expires_at, scope=grant.scope)


def consume_grant(db: Session, *, session_id: str, token: str, required_scope: str = "chat-restricted") -> bool:
    if not token or not settings.emergency_break_glass_enabled:
        return False
    now = _utcnow()
    grants = db.scalars(select(BreakGlassGrant).where(
        BreakGlassGrant.session_id == session_id,
        BreakGlassGrant.used.is_(False),
        BreakGlassGrant.revoked.is_(False),
        BreakGlassGrant.expires_at >= now,
        BreakGlassGrant.scope == required_scope,
    ).order_by(BreakGlassGrant.issued_at.desc())).all()

    for grant in grants:
        if verify_secret(token, grant.token_salt, grant.token_hash, grant.hash_iterations):
            grant.used = True
            _log_event(db, event_type="break_glass_consumed", session_id=session_id, decision="authorized", category="break_glass", detail="grant consumido para solicitação restrita", grant_id=grant.id)
            db.commit()
            return True
    return False


def revoke_grant(db: Session, grant_id: int, session_id: str | None = None) -> bool:
    stmt = select(BreakGlassGrant).where(BreakGlassGrant.id == grant_id)
    if session_id is not None:
        stmt = stmt.where(BreakGlassGrant.session_id == session_id)
    grant = db.scalar(stmt)
    if not grant:
        return False
    grant.revoked = True
    db.commit()
    return True


def revoke_all(db: Session) -> int:
    grants = db.scalars(select(BreakGlassGrant).where(BreakGlassGrant.revoked.is_(False))).all()
    count = 0
    for grant in grants:
        grant.revoked = True
        count += 1
    if count:
        db.commit()
    return count


def status(db: Session) -> dict:
    creds = active_credentials(db)
    now = _utcnow()
    grants = db.scalars(select(BreakGlassGrant).where(BreakGlassGrant.revoked.is_(False), BreakGlassGrant.expires_at >= now)).all()
    return {
        "enabled": bool(settings.emergency_break_glass_enabled),
        "registered_credentials": len(creds),
        "active_grants": len(grants),
        "grant_minutes": settings.emergency_session_minutes,
        "max_attempts": settings.emergency_max_attempts,
        "cooldown_minutes": settings.emergency_cooldown_minutes,
        "hard_blocks_overridable": False,
    }
