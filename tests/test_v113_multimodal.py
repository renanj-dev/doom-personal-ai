import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi.testclient import TestClient
import pytest

from app.config import get_settings
from app.multimodal import VisionError, validate_image, VisionResult
from app.main import app


def test_v113_version_and_ui():
    c = TestClient(app)
    h = c.get('/health')
    assert h.json()['version'] == '1.13.1'
    html = c.get('/').text
    assert 'FOREST CORE · v1.13.1' in html
    assert '/static/doom-state.js?v=1.13.1' in html
    assert 'id="imageBtn"' in html
    assert 'id="micBtn"' in html


def test_image_validation_accepts_supported_formats(monkeypatch):
    monkeypatch.setattr(get_settings(), 'multimodal_enabled', True)
    monkeypatch.setattr(get_settings(), 'vision_max_file_mb', 2)
    assert validate_image(b'123', 'image/png', 'x.png') == 'image/png'
    assert validate_image(b'123', '', 'x.webp') == 'image/webp'


def test_image_validation_rejects_unsupported_and_oversized(monkeypatch):
    monkeypatch.setattr(get_settings(), 'multimodal_enabled', True)
    monkeypatch.setattr(get_settings(), 'vision_max_file_mb', 1)
    with pytest.raises(VisionError):
        validate_image(b'123', 'text/plain', 'x.txt')
    with pytest.raises(VisionError):
        validate_image(b'x'*(1024*1024+1), 'image/png', 'x.png')


def test_multimodal_status_requires_configured_vision_model(monkeypatch):
    from app.multimodal import status
    st = get_settings()
    monkeypatch.setattr(st, 'multimodal_enabled', True)
    monkeypatch.setattr(st, 'openai_api_key', 'test')
    monkeypatch.setattr(st, 'openai_vision_model', None)
    monkeypatch.setattr(st, 'openrouter_api_key', None)
    monkeypatch.setattr(st, 'openrouter_vision_model', None)
    monkeypatch.setattr(st, 'ollama_vision_model', None)
    data = status()
    assert data['vision'] is False
    assert data['providers'] == []


def test_multimodal_status_route_requires_auth(monkeypatch):
    c = TestClient(app)
    r = c.get('/api/multimodal/status')
    assert r.status_code == 401



def test_vision_chat_route_persists_reply_and_uses_current_image(monkeypatch):
    from app.main import analyze_image
    monkeypatch.setattr('app.main.analyze_image', lambda *args, **kwargs: VisionResult('Vi uma questão de matemática.', 'mock', 'vision-test'))
    c = TestClient(app)
    h = {'X-Doom-Key': 'test-key'}
    r = c.post('/api/chat/vision', headers=h, data={'message':'Explique a questão da imagem.', 'session_id':'vision-test'}, files={'image':('questao.png', b'\x89PNG\r\n\x1a\nabc', 'image/png')})
    assert r.status_code == 200
    body = r.json()
    assert body['vision_used'] is True
    assert body['vision_provider'] == 'mock'
    assert 'matemática' in body['reply']


def test_v1131_frontend_multimodal_state_and_wiring():
    js = Path(__file__).resolve().parents[1] / 'app' / 'static' / 'doom-state.js'
    text = js.read_text(encoding='utf-8')
    assert "const DOOM_MULTIMODAL =" in text
    assert "let DOOM_IMAGE_FILE = null;" in text
    assert "addEventListener('click',toggleListening)" in text
    assert "addEventListener('click',toggleVoiceOutput)" in text
    assert "addEventListener('click',selectImage)" in text
