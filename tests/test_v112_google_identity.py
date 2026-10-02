import os, time
os.environ.setdefault("DOOM_API_KEY", "test-key")

import jwt
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from app.identity import verify_google_id_token


def test_google_feature_configuration_is_optional(monkeypatch):
    from app.config import Settings
    s = Settings(DOOM_API_KEY="x", GOOGLE_LOGIN_ENABLED=False, GOOGLE_CLIENT_ID="")
    assert s.google_login_enabled is False
    assert s.google_client_id == ""


def test_google_token_verifier_rejects_when_disabled(monkeypatch):
    import app.identity as identity
    monkeypatch.setattr(identity.settings, "google_login_enabled", False)
    monkeypatch.setattr(identity.settings, "google_client_id", "")
    try:
        verify_google_id_token("not-a-token")
    except ValueError as exc:
        assert "não está configurado" in str(exc)
    else:
        raise AssertionError("token inválido deveria falhar")


def test_google_token_verifier_accepts_valid_mock_token(monkeypatch):
    import app.identity as identity
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(identity.settings, "google_login_enabled", True)
    monkeypatch.setattr(identity.settings, "google_client_id", "client-123")
    class FakeSigningKey:
        key = pem
    class FakeJwkClient:
        def __init__(self, *args, **kwargs): pass
        def get_signing_key_from_jwt(self, token): return FakeSigningKey()
    monkeypatch.setattr(identity.jwt, "PyJWKClient", FakeJwkClient)
    now=int(time.time())
    token=jwt.encode({"sub":"google-sub-1","aud":"client-123","iss":"https://accounts.google.com","exp":now+300,"email":"user@gmail.com","email_verified":True}, private, algorithm="RS256")
    payload=verify_google_id_token(token)
    assert payload["sub"]=="google-sub-1"


def test_google_token_verifier_rejects_wrong_audience(monkeypatch):
    import app.identity as identity
    private = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public = private.public_key()
    pem = public.public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
    monkeypatch.setattr(identity.settings, "google_login_enabled", True)
    monkeypatch.setattr(identity.settings, "google_client_id", "client-123")
    class FakeSigningKey: key=pem
    class FakeJwkClient:
        def __init__(self,*a,**k): pass
        def get_signing_key_from_jwt(self, token): return FakeSigningKey()
    monkeypatch.setattr(identity.jwt, "PyJWKClient", FakeJwkClient)
    token=jwt.encode({"sub":"google-sub-2","aud":"other-client","iss":"https://accounts.google.com","exp":int(time.time())+300}, private, algorithm="RS256")
    try:
        verify_google_id_token(token)
    except ValueError as exc:
        assert "inválido" in str(exc) or "expirado" in str(exc)
    else:
        raise AssertionError("audience incorreta deveria falhar")
