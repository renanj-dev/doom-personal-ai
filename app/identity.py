from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
import hashlib
import secrets
import jwt

import uuid

from sqlalchemy import select
from .config import get_settings
from .db import SessionLocal
from .models import UserIdentity, ApiKeyRecord, UserSession, GoogleIdentity

settings = get_settings()

SESSION_COOKIE_NAME = "doom_session"


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _user_public(row: UserIdentity) -> dict:
    return {
        "user_id": row.user_id,
        "username": row.username,
        "display_name": row.display_name,
        "active": bool(row.active),
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


GOOGLE_ISSUERS = {"accounts.google.com", "https://accounts.google.com"}
GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

def _google_client_configured() -> bool:
    return bool(settings.google_login_enabled and settings.google_client_id.strip())

def verify_google_id_token(token: str) -> dict:
    if not _google_client_configured():
        raise ValueError("Login com Google não está configurado no servidor.")
    try:
        header = jwt.get_unverified_header(token)
        alg = header.get("alg")
        if alg != "RS256":
            raise ValueError("Algoritmo do token Google não permitido.")
        jwks = jwt.PyJWKClient(GOOGLE_JWKS_URL, cache_jwk_set=True)
        signing_key = jwks.get_signing_key_from_jwt(token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            audience=settings.google_client_id.strip(),
            issuer=GOOGLE_ISSUERS,
            options={"require": ["sub", "aud", "iss", "exp"]},
        )
    except Exception as exc:
        raise ValueError("Token de identidade do Google inválido ou expirado.") from exc
    if not payload.get("sub"):
        raise ValueError("Token Google sem identificador estável.")
    if payload.get("email") and payload.get("email_verified") is False:
        raise ValueError("A identidade do Google não possui e-mail verificado.")
    return payload


def _new_session(db, principal: "Principal", user_agent: str | None) -> tuple[str, "Principal", datetime]:
    raw = "dsess_" + secrets.token_urlsafe(48)
    now = _now()
    expires = now + timedelta(hours=max(1, settings.security_session_hours))
    db.add(UserSession(
        session_id=f"sess_{uuid.uuid4().hex}",
        token_hash=_hash_secret(raw),
        user_id=principal.user_id,
        created_at=now,
        expires_at=expires,
        revoked_at=None,
        user_agent=(user_agent or "")[:300],
    ))
    return raw, Principal(principal.user_id, principal.username, principal.display_name, "session"), expires


@dataclass(frozen=True)
class Principal:
    user_id: str
    username: str
    display_name: str
    auth_method: str
    session_id: str | None = None


class IdentityEngine:
    def bootstrap(self) -> UserIdentity:
        """Ensure the configured Doom owner exists and its API key is registered by hash."""
        with SessionLocal() as db:
            user = db.scalar(select(UserIdentity).where(UserIdentity.username == settings.doom_user_name))
            now = _now()
            if user is None:
                user = UserIdentity(
                    user_id=f"usr_{uuid.uuid4().hex}",
                    username=settings.doom_user_name,
                    display_name=settings.doom_user_name,
                    active=True,
                    created_at=now,
                    updated_at=now,
                )
                db.add(user)
                db.flush()
            elif not user.active:
                user.active = True
                user.updated_at = now

            key_hash = _hash_secret(settings.doom_api_key)
            key_row = db.scalar(select(ApiKeyRecord).where(ApiKeyRecord.key_hash == key_hash))
            if key_row is None:
                db.add(ApiKeyRecord(
                    key_id=f"key_{uuid.uuid4().hex}",
                    user_id=user.user_id,
                    key_prefix=settings.doom_api_key[:8],
                    key_hash=key_hash,
                    active=True,
                    created_at=now,
                    last_used_at=None,
                ))
            elif not key_row.active or key_row.user_id != user.user_id:
                key_row.active = True
                key_row.user_id = user.user_id
                key_row.last_used_at = now
            db.commit()
            db.refresh(user)
            return user

    def authenticate_api_key(self, credential: str | None) -> Principal | None:
        if not credential:
            return None
        # Register the configured bootstrap key before opening the authentication transaction.
        # This avoids nested write transactions on SQLite/PostgreSQL during first use.
        if secrets.compare_digest(credential, settings.doom_api_key):
            self.bootstrap()
        key_hash = _hash_secret(credential)
        with SessionLocal() as db:
            row = db.scalar(
                select(ApiKeyRecord).where(ApiKeyRecord.key_hash == key_hash, ApiKeyRecord.active.is_(True))
            )
            if row is None:
                return None
            user = db.scalar(select(UserIdentity).where(UserIdentity.user_id == row.user_id, UserIdentity.active.is_(True)))
            if user is None:
                return None
            row.last_used_at = _now()
            db.commit()
            return Principal(user.user_id, user.username, user.display_name, "api_key")

    def create_session(self, credential: str | None, user_agent: str | None = None) -> tuple[str, Principal, datetime] | None:
        principal = self.authenticate_api_key(credential)
        if principal is None:
            return None
        with SessionLocal() as db:
            result = _new_session(db, principal, user_agent)
            db.commit()
            return result

    def link_google_identity(self, token: str, principal: Principal) -> dict:
        payload = verify_google_id_token(token)
        google_sub = str(payload["sub"])
        email = str(payload.get("email") or "")[:320]
        display_name = str(payload.get("name") or email or principal.display_name)[:160]
        picture_url = str(payload.get("picture") or "")[:1000]
        now = _now()
        with SessionLocal() as db:
            row = db.scalar(select(GoogleIdentity).where(GoogleIdentity.google_sub == google_sub))
            if row is not None and row.user_id != principal.user_id:
                raise ValueError("Esta conta Google já está vinculada a outra identidade Doom.")
            if row is None:
                row = GoogleIdentity(google_sub=google_sub, user_id=principal.user_id, email=email, display_name=display_name, picture_url=picture_url, created_at=now, updated_at=now)
                db.add(row)
            else:
                row.email=email; row.display_name=display_name; row.picture_url=picture_url; row.updated_at=now
            db.commit()
            return {"linked": True, "google_sub": google_sub, "email": email, "display_name": display_name, "picture_url": picture_url}

    def create_session_from_google(self, token: str, user_agent: str | None = None) -> tuple[str, Principal, datetime] | None:
        payload = verify_google_id_token(token)
        google_sub = str(payload["sub"])
        with SessionLocal() as db:
            row = db.scalar(select(GoogleIdentity).where(GoogleIdentity.google_sub == google_sub))
            if row is None:
                raise LookupError("Esta conta Google ainda não está vinculada ao Doom. Entre com sua Chave Doom e use 'Vincular Google'.")
            user = db.scalar(select(UserIdentity).where(UserIdentity.user_id == row.user_id, UserIdentity.active.is_(True)))
            if user is None:
                raise LookupError("A identidade Doom vinculada a esta conta não está ativa.")
            result = _new_session(db, Principal(user.user_id, user.username, user.display_name, "google"), user_agent)
            db.commit()
            return result

    def google_identity(self, user_id: str) -> dict | None:
        with SessionLocal() as db:
            row = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == user_id))
            if row is None:
                return None
            return {"linked": True, "google_sub": row.google_sub, "email": row.email, "display_name": row.display_name, "picture_url": row.picture_url, "created_at": row.created_at, "updated_at": row.updated_at}

    def unlink_google_identity(self, principal: Principal) -> bool:
        with SessionLocal() as db:
            row = db.scalar(select(GoogleIdentity).where(GoogleIdentity.user_id == principal.user_id))
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def authenticate_session(self, token: str | None) -> Principal | None:
        if not token:
            return None
        token_hash = _hash_secret(token)
        now = _now()
        with SessionLocal() as db:
            row = db.scalar(select(UserSession).where(UserSession.token_hash == token_hash))
            if row is None or row.revoked_at is not None:
                return None
            expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
            if expires <= now:
                return None
            user = db.scalar(select(UserIdentity).where(UserIdentity.user_id == row.user_id, UserIdentity.active.is_(True)))
            if user is None:
                return None
            return Principal(user.user_id, user.username, user.display_name, "session", row.session_id)

    def revoke_session(self, token: str | None, user_id: str | None = None) -> bool:
        if not token:
            return False
        with SessionLocal() as db:
            row = db.scalar(select(UserSession).where(UserSession.token_hash == _hash_secret(token)))
            if row is None or (user_id is not None and row.user_id != user_id):
                return False
            if row.revoked_at is None:
                row.revoked_at = _now()
                db.commit()
            return True

    def revoke_all_sessions(self, user_id: str) -> int:
        now = _now()
        with SessionLocal() as db:
            rows = db.scalars(select(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))).all()
            for row in rows:
                row.revoked_at = now
            db.commit()
            return len(rows)

    def me(self, principal: Principal) -> dict:
        with SessionLocal() as db:
            user = db.scalar(select(UserIdentity).where(UserIdentity.user_id == principal.user_id))
            if user is None:
                raise ValueError("Identidade não encontrada.")
            return {
                **_user_public(user),
                "auth_method": principal.auth_method,
                "session_id": principal.session_id,
                "session_hours": max(1, settings.security_session_hours) if principal.auth_method == "session" else None,
                "mode": "single_user_owner",
            }

    def active_sessions(self, user_id: str) -> list[dict]:
        now = _now()
        with SessionLocal() as db:
            rows = db.scalars(
                select(UserSession).where(UserSession.user_id == user_id).order_by(UserSession.created_at.desc())
            ).all()
            result = []
            for row in rows:
                expires = row.expires_at.replace(tzinfo=timezone.utc) if row.expires_at.tzinfo is None else row.expires_at
                result.append({
                    "session_id": row.session_id,
                    "created_at": row.created_at,
                    "expires_at": row.expires_at,
                    "revoked": row.revoked_at is not None,
                    "expired": expires <= now,
                    "user_agent": row.user_agent,
                })
            return result


IDENTITY_ENGINE = IdentityEngine()
