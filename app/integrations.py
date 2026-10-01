from __future__ import annotations

import ipaddress
import json
import os
import socket
from dataclasses import dataclass
from datetime import datetime, timezone
from urllib.parse import urljoin, urlsplit

import httpx
from sqlalchemy import select

from .config import get_settings
from .db import SessionLocal
from .models import ExternalIntegration

settings = get_settings()

_ALLOWED_METHODS = {"GET", "POST", "PUT", "PATCH", "DELETE"}
_LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}


class IntegrationError(ValueError):
    pass


@dataclass(frozen=True)
class IntegrationSpec:
    name: str
    kind: str
    base_url: str
    allowed_paths: tuple[str, ...]
    allowed_methods: tuple[str, ...]
    auth_env_var: str
    auth_header: str
    enabled: bool
    timeout_seconds: float


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _split_csv(value: str | None, upper: bool = False) -> tuple[str, ...]:
    items = []
    for raw in (value or "").split(","):
        item = raw.strip()
        if not item:
            continue
        items.append(item.upper() if upper else item)
    return tuple(dict.fromkeys(items))


def _validate_base_url(base_url: str) -> str:
    raw = (base_url or "").strip()
    parts = urlsplit(raw)
    if parts.scheme not in {"https", "http"} or not parts.netloc:
        raise IntegrationError("A URL base da integração deve usar http:// ou https:// e conter um host.")
    if parts.username or parts.password or parts.query or parts.fragment:
        raise IntegrationError("A URL base não pode conter usuário, senha, query ou fragmento.")
    host = (parts.hostname or "").lower().rstrip(".")
    if not host:
        raise IntegrationError("Host inválido para a integração.")
    if parts.scheme == "http" and not settings.integrations_allow_private and host not in _LOCAL_HOSTS:
        raise IntegrationError("Integrações HTTP sem TLS são permitidas somente para hosts locais quando habilitadas.")
    _validate_host_resolution(host)
    base_path = parts.path or "/"
    if not base_path.startswith("/"):
        base_path = "/" + base_path
    if not base_path.endswith("/"):
        base_path += "/"
    return f"{parts.scheme}://{parts.netloc}{base_path}"


def _validate_host_resolution(host: str) -> None:
    try:
        direct = ipaddress.ip_address(host)
        addresses = [direct]
    except ValueError:
        try:
            infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
        except OSError as exc:
            raise IntegrationError("Não foi possível resolver o host da integração.") from exc
        addresses = []
        for info in infos:
            try:
                addresses.append(ipaddress.ip_address(info[4][0]))
            except ValueError:
                continue
    if not addresses:
        raise IntegrationError("O host da integração não possui endereço válido.")
    if not settings.integrations_allow_private:
        allow_loopback = host.lower().rstrip(".") in _LOCAL_HOSTS
        for addr in addresses:
            if (addr.is_private or addr.is_loopback or addr.is_link_local or addr.is_reserved or addr.is_multicast) and not (allow_loopback and addr.is_loopback):
                raise IntegrationError("O host resolve para uma rede privada/local; habilite integrações privadas explicitamente para usá-lo.")


def _validate_path(path: str) -> str:
    value = (path or "/").strip()
    if not value.startswith("/"):
        raise IntegrationError("O caminho precisa começar com '/'.")
    if len(value) > 600:
        raise IntegrationError("Caminho longo demais.")
    parts = urlsplit(value)
    if parts.scheme or parts.netloc:
        raise IntegrationError("O caminho não pode conter uma URL absoluta.")
    if "\\" in value or ".." in value.split("/"):
        raise IntegrationError("Caminho inválido.")
    return value


def _path_allowed(path: str, prefixes: tuple[str, ...]) -> bool:
    if not prefixes:
        return path == "/"
    return any(path == prefix or path.startswith(prefix.rstrip("/") + "/") for prefix in prefixes)


def _sanitize_response_headers(headers: httpx.Headers) -> dict[str, str]:
    allowed = {"content-type", "location", "etag", "cache-control"}
    return {k: v for k, v in headers.items() if k.lower() in allowed}


def _parse_json_or_text(response: httpx.Response) -> object:
    content = response.text[: max(1, int(settings.integrations_max_response_chars))]
    content_type = response.headers.get("content-type", "").lower()
    if "json" in content_type:
        try:
            return response.json()
        except Exception:
            pass
    return content


class IntegrationEngine:
    def list(self) -> list[dict]:
        with SessionLocal() as db:
            rows = db.scalars(select(ExternalIntegration).order_by(ExternalIntegration.name.asc())).all()
            return [self._public(row) for row in rows]

    def get(self, name: str) -> ExternalIntegration | None:
        with SessionLocal() as db:
            return db.scalar(select(ExternalIntegration).where(ExternalIntegration.name == name.strip()))

    def get_in_session(self, db, name: str) -> ExternalIntegration | None:
        return db.scalar(select(ExternalIntegration).where(ExternalIntegration.name == name.strip()))

    @staticmethod
    def _public(row: ExternalIntegration) -> dict:
        return {
            "id": row.id,
            "name": row.name,
            "kind": row.kind,
            "base_url": row.base_url,
            "allowed_paths": list(_split_csv(row.allowed_paths)),
            "allowed_methods": list(_split_csv(row.allowed_methods, upper=True)),
            "auth_env_var": row.auth_env_var or "",
            "auth_header": row.auth_header or "Authorization",
            "enabled": bool(row.enabled),
            "timeout_seconds": row.timeout_seconds,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "last_test_status": row.last_test_status or "",
            "last_test_at": row.last_test_at,
        }

    def register(
        self,
        *,
        name: str,
        kind: str = "http_json",
        base_url: str,
        allowed_paths: list[str] | None = None,
        allowed_methods: list[str] | None = None,
        auth_env_var: str = "",
        auth_header: str = "Authorization",
        enabled: bool = True,
        timeout_seconds: float | None = None,
    ) -> dict:
        clean_name = (name or "").strip()
        if not clean_name or len(clean_name) > 80 or any(ch not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for ch in clean_name):
            raise IntegrationError("Nome inválido. Use até 80 caracteres: letras, números, '_' ou '-'.")
        if kind != "http_json":
            raise IntegrationError("No v1.9, o único tipo disponível é http_json.")
        clean_base = _validate_base_url(base_url)
        paths = tuple(_validate_path(p) for p in (allowed_paths or ["/"]))
        methods = _split_csv(",".join(allowed_methods or ["GET"]), upper=True)
        if not methods or any(m not in _ALLOWED_METHODS for m in methods):
            raise IntegrationError("Métodos inválidos. Use GET, POST, PUT, PATCH ou DELETE.")
        auth_env = (auth_env_var or "").strip()
        if auth_env and not auth_env.replace("_", "A").isalnum():
            raise IntegrationError("Variável de ambiente de segredo inválida.")
        header = (auth_header or "Authorization").strip()
        if len(header) > 100 or any(c in header for c in "\r\n:"):
            raise IntegrationError("Nome de cabeçalho de autenticação inválido.")
        timeout = float(timeout_seconds if timeout_seconds is not None else settings.integrations_default_timeout)
        timeout = max(0.5, min(timeout, 30.0))
        now = _utcnow()
        with SessionLocal() as db:
            row = db.scalar(select(ExternalIntegration).where(ExternalIntegration.name == clean_name))
            if row is None:
                row = ExternalIntegration(
                    name=clean_name,
                    kind=kind,
                    base_url=clean_base,
                    allowed_paths=", ".join(paths),
                    allowed_methods=", ".join(methods),
                    auth_env_var=auth_env,
                    auth_header=header,
                    enabled=bool(enabled),
                    timeout_seconds=timeout,
                    created_at=now,
                    updated_at=now,
                    last_test_status="",
                    last_test_at=None,
                )
                db.add(row)
            else:
                row.kind = kind
                row.base_url = clean_base
                row.allowed_paths = ", ".join(paths)
                row.allowed_methods = ", ".join(methods)
                row.auth_env_var = auth_env
                row.auth_header = header
                row.enabled = bool(enabled)
                row.timeout_seconds = timeout
                row.updated_at = now
            db.commit()
            db.refresh(row)
            return self._public(row)

    def set_enabled(self, name: str, enabled: bool) -> dict:
        with SessionLocal() as db:
            row = self.get_in_session(db, name)
            if row is None:
                raise IntegrationError("Integração não encontrada.")
            row.enabled = bool(enabled)
            row.updated_at = _utcnow()
            db.commit()
            db.refresh(row)
            return self._public(row)

    def delete(self, name: str) -> bool:
        with SessionLocal() as db:
            row = self.get_in_session(db, name)
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True

    def request(self, *, integration: str, method: str, path: str = "/", query: dict | None = None, body: object | None = None) -> dict:
        if not settings.integrations_enabled:
            raise IntegrationError("Integrações externas estão desativadas na configuração do servidor.")
        name = (integration or "").strip()
        method = (method or "GET").strip().upper()
        if not name:
            raise IntegrationError("Informe o nome da integração.")
        path = _validate_path(path)
        if method not in _ALLOWED_METHODS:
            raise IntegrationError("Método HTTP não permitido.")
        if query is not None and not isinstance(query, dict):
            raise IntegrationError("Query precisa ser um objeto JSON.")
        body_text = ""
        if body is not None:
            try:
                body_text = json.dumps(body, ensure_ascii=False)
            except (TypeError, ValueError) as exc:
                raise IntegrationError("Body não é JSON serializável.") from exc
            if len(body_text) > settings.integrations_max_body_chars:
                raise IntegrationError("Body excede o limite permitido.")

        with SessionLocal() as db:
            row = self.get_in_session(db, name)
            if row is None:
                raise IntegrationError("Integração não encontrada.")
            if not row.enabled:
                raise IntegrationError("A integração está desativada.")
            methods = _split_csv(row.allowed_methods, upper=True)
            prefixes = _split_csv(row.allowed_paths)
            if method not in methods:
                raise IntegrationError(f"O método {method} não está permitido para esta integração.")
            if not _path_allowed(path, prefixes):
                raise IntegrationError("O caminho solicitado não está na lista permitida.")
            base_url = _validate_base_url(row.base_url)
            auth_env = row.auth_env_var or ""
            auth_header = row.auth_header or "Authorization"
            secret_value = os.getenv(auth_env) if auth_env else ""

        target = urljoin(base_url, path.lstrip("/"))
        target_parts = urlsplit(target)
        _validate_host_resolution(target_parts.hostname or "")
        headers = {"Accept": "application/json", "User-Agent": "Doom-External-Integration/1.9"}
        if body is not None:
            headers["Content-Type"] = "application/json"
        if auth_env:
            if not secret_value:
                raise IntegrationError(f"A variável de segredo {auth_env} não está configurada no ambiente do servidor.")
            headers[auth_header] = secret_value

        timeout = httpx.Timeout(max(0.5, min(float(row.timeout_seconds), 30.0)))
        with httpx.Client(timeout=timeout, follow_redirects=False) as client:
            response = client.request(method, target, params=query or {}, headers=headers, json=body)
        return {
            "integration": name,
            "method": method,
            "path": path,
            "status_code": response.status_code,
            "ok": 200 <= response.status_code < 400,
            "headers": _sanitize_response_headers(response.headers),
            "data": _parse_json_or_text(response),
        }

    def test(self, name: str) -> dict:
        result = self.request(integration=name, method="GET", path="/")
        with SessionLocal() as db:
            row = self.get_in_session(db, name)
            if row:
                row.last_test_status = "ok" if result.get("ok") else "error"
                row.last_test_at = _utcnow()
                row.updated_at = _utcnow()
                db.commit()
        return result


INTEGRATION_ENGINE = IntegrationEngine()


def external_http_request(integration: str, method: str, path: str = "/", query: dict | None = None, body: object | None = None):
    return INTEGRATION_ENGINE.request(
        integration=integration,
        method=method,
        path=path,
        query=query,
        body=body,
    )
