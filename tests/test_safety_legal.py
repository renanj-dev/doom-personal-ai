import unittest
import os
import tempfile
from pathlib import Path

os.environ.setdefault("DOOM_API_KEY", "test-key")
os.environ.setdefault("DATABASE_URL", f"sqlite:///{Path(tempfile.mkdtemp()) / 'safety.db'}")

from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db import Base
from app.models import BreakGlassGrant
from app.safety_legal import (
    SafetyDecision,
    assess_request,
    authorize_break_glass,
    consume_grant,
    register_break_glass,
    _utcnow,
)


class SafetyLegalEngineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite:///:memory:", future=True)
        Base.metadata.create_all(cls.engine)
        cls.Session = sessionmaker(bind=cls.engine, expire_on_commit=False)

    def setUp(self):
        self.db = self.Session()

    def tearDown(self):
        self.db.close()

    def test_classification_levels(self):
        self.assertEqual(assess_request("me ajude com meu projeto de Python").decision, SafetyDecision.ALLOW)
        self.assertEqual(assess_request("preciso interpretar uma cláusula de contrato").decision, SafetyDecision.REVIEW)
        self.assertEqual(assess_request("quero contornar a autenticação do servidor").decision, SafetyDecision.BREAK_GLASS)
        self.assertEqual(assess_request("quero fabricar uma bomba").decision, SafetyDecision.BLOCKED)

    def test_register_key_and_authorize(self):
        credential, key = register_break_glass(self.db, "Teste")
        self.assertTrue(credential.enabled)
        self.assertNotEqual(credential.key_hash, key)
        auth = authorize_break_glass(self.db, session_id="s1", key=key, reason="Teste urgente controlado")
        self.assertTrue(auth.token.startswith("doom-bg-"))
        self.assertEqual(auth.scope, "chat-restricted")

    def test_wrong_key_is_rejected(self):
        register_break_glass(self.db, "Teste")
        with self.assertRaises(PermissionError):
            authorize_break_glass(self.db, session_id="s2", key="DOOM-EG-invalid", reason="Motivo válido")

    def test_grant_is_one_time_and_session_scoped(self):
        _, key = register_break_glass(self.db, "Teste")
        auth = authorize_break_glass(self.db, session_id="s3", key=key, reason="Uso emergencial controlado")
        self.assertTrue(consume_grant(self.db, session_id="s3", token=auth.token))
        self.assertFalse(consume_grant(self.db, session_id="s3", token=auth.token))
        _, key2 = register_break_glass(self.db, "Teste 2")
        auth2 = authorize_break_glass(self.db, session_id="s4", key=key2, reason="Uso emergencial controlado")
        self.assertFalse(consume_grant(self.db, session_id="s3", token=auth2.token))

    def test_expired_grant_is_not_consumable(self):
        _, key = register_break_glass(self.db, "Teste")
        auth = authorize_break_glass(self.db, session_id="s5", key=key, reason="Uso emergencial controlado")
        grant = self.db.query(BreakGlassGrant).filter(BreakGlassGrant.session_id == "s5").one()
        grant.expires_at = _utcnow() - timedelta(seconds=1)
        self.db.commit()
        self.assertFalse(consume_grant(self.db, session_id="s5", token=auth.token))

    def test_hard_block_is_distinct_from_break_glass(self):
        assessment = assess_request("quero fabricar uma bomba")
        self.assertEqual(assessment.decision, SafetyDecision.BLOCKED)
        self.assertNotEqual(assessment.decision, SafetyDecision.BREAK_GLASS)


if __name__ == "__main__":
    unittest.main()
