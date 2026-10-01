import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ.setdefault("DOOM_API_KEY", "test")

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from app.db import Base
from app.models import Message, Memory
from app.context_engine import build_context
from app.llm import _messages


class ContextEngineTests(unittest.TestCase):
    def _db(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        return engine, sessionmaker(bind=engine), path

    def test_relevant_cross_conversation_recall(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                db.add_all([
                    Message(session_id="current", role="user", content="Estamos trabalhando no Doom Cortex."),
                    Message(session_id="other", role="user", content="Na conversa antiga decidimos usar Forest Core no layout da Doom."),
                    Memory(category="projeto_doom", content="A identidade visual da Doom usa verde-floresta."),
                ])
                db.commit()
                bundle = build_context(db, "current", "Como ficou o Forest Core da Doom?")
                self.assertEqual(bundle.recent_count, 1)
                self.assertGreaterEqual(bundle.recalled_count, 1)
                self.assertGreaterEqual(bundle.memory_count, 1)
                self.assertTrue(all(m["role"] == "user" for m in bundle.recalled_messages))
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_greeting_isolated_from_previous_topic(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                db.add_all([
                    Message(session_id="main", role="user", content="Explique minhas férias na CLT."),
                    Message(session_id="main", role="assistant", content="Resposta detalhada sobre férias."),
                    Message(session_id="main", role="user", content="Boa noite Doom"),
                ])
                db.commit()
                bundle = build_context(db, "main", "Boa noite Doom")
                self.assertEqual(bundle.recent_count, 1)
                self.assertEqual(bundle.recent_messages[0]["content"], "Boa noite Doom")
                self.assertTrue(all(m["role"] == "user" for m in bundle.recalled_messages))
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_identity_query_isolated_from_previous_topic(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                db.add_all([
                    Message(session_id="main", role="user", content="Qual a diferença entre arranjo e combinação?"),
                    Message(session_id="main", role="assistant", content="Uma explicação longa de matemática."),
                    Message(session_id="main", role="user", content="Doom, apresente-se"),
                ])
                db.commit()
                bundle = build_context(db, "main", "Doom, apresente-se")
                self.assertEqual(bundle.recent_count, 1)
                self.assertEqual(bundle.recent_messages[0]["content"], "Doom, apresente-se")
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass

    def test_memory_query_can_recall_user_statement_but_not_old_answer(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                db.add_all([
                    Message(session_id="old", role="user", content="Meu professor se chama Schypriann e ele dá matemática."),
                    Message(session_id="old", role="assistant", content="CLT: férias são 30 dias corridos."),
                    Message(session_id="main", role="user", content="Doom lembra do meu professor Schypriann?"),
                ])
                db.commit()
                bundle = build_context(db, "main", "Doom lembra do meu professor Schypriann?")
                self.assertEqual(bundle.recent_count, 1)
                self.assertTrue(any("Schypriann" in m["content"] for m in bundle.recalled_messages))
                self.assertTrue(all("CLT" not in m["content"] for m in bundle.recalled_messages))
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


    def test_current_request_is_the_final_llm_turn(self):
        history = [
            {"role": "user", "content": "Explique minhas férias na CLT."},
            {"role": "assistant", "content": "Resposta sobre CLT."},
        ]
        current_request = {"role": "user", "content": "Doom, apresente-se"}
        messages = _messages(
            "[projeto_doom] Memória antiga sobre o currículo do Doom.",
            history + [current_request],
            profile_text="PERFIL DE APOIO",
        )
        self.assertEqual(messages[-1], current_request)


    def test_cortex_marks_current_request_explicitly(self):
        from unittest.mock import patch
        import app.cortex as cortex
        with patch.object(cortex, "configured_providers", return_value=["ollama"]), \
             patch.object(cortex, "provider_available", return_value=True), \
             patch.object(cortex, "provider_model", return_value="test-model"), \
             patch.object(cortex, "ask_doom", return_value="Resposta direta.") as mocked:
            cortex.ask_with_cortex(
                memory_text="memória antiga",
                recent_messages=[{"role": "assistant", "content": "Resposta anterior."}],
                user_message="Doom, apresente-se",
                profile_text="perfil",
                session_id="main",
            )
            sent = mocked.call_args.args[1]
            self.assertTrue(sent[-1]["content"].startswith("CURRENT_USER_REQUEST\n"))
            self.assertIn("Doom, apresente-se", sent[-1]["content"])

    def test_unrelated_memories_are_not_backfilled(self):
        engine, Session, path = self._db()
        try:
            with Session() as db:
                db.add_all([
                    Memory(category="trabalho", content="Currículo para vaga administrativa."),
                    Memory(category="tecnologia", content="O Doom usa Python."),
                ])
                db.commit()
                bundle = build_context(db, "main", "Boa noite Doom")
                self.assertEqual(bundle.memory_count, 0)
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
