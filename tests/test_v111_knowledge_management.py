from fastapi.testclient import TestClient
from app.main import app
from app.db import SessionLocal
from app.knowledge_engine import KNOWLEDGE_ENGINE


def _key(client):
    return 'test-key'


def test_v111_health_and_ui_version():
    with TestClient(app) as client:
        r = client.get('/health')
        assert r.status_code == 200
        assert r.json()['version'] == '1.13.2'
        html = client.get('/').text
        assert 'FOREST CORE · v1.13.2' in html
        assert '/static/doom-state.js?v=1.13.2' in html


def test_v111_catalog_and_filtered_list():
    db = SessionLocal()
    try:
        doc = KNOWLEDGE_ENGINE.create_text(db, title='Álgebra', content='Equações de primeiro grau', collection='Estudos', topic='Matemática', version='2')
    finally:
        db.close()
    with TestClient(app) as client:
        # auth dependency in the project accepts the legacy key configured by tests
        h={'X-Doom-Key': _key(client)}
        cat=client.get('/api/knowledge/catalog', headers=h)
        assert cat.status_code == 200
        assert any(x['name']=='Estudos' for x in cat.json()['collections'])
        rows=client.get('/api/knowledge', params={'collection':'Estudos'}, headers=h)
        assert rows.status_code == 200
        assert any(x['id']==doc.id for x in rows.json())


def test_v111_detail_contains_full_content_and_reindex():
    db = SessionLocal()
    try:
        doc = KNOWLEDGE_ENGINE.create_text(db, title='Reindex Test', content='Conteúdo original para reindexação', collection='Testes')
        doc_id=doc.id
    finally:
        db.close()
    with TestClient(app) as client:
        h={'X-Doom-Key': _key(client)}
        detail=client.get(f'/api/knowledge/{doc_id}', headers=h)
        assert detail.status_code == 200
        assert detail.json()['content'] == 'Conteúdo original para reindexação'
        idx=client.post(f'/api/knowledge/{doc_id}/reindex', headers=h)
        assert idx.status_code == 200
        assert idx.json()['id'] == doc_id
