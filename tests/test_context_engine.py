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


class ContextEngineTests(unittest.TestCase):
    def test_relevant_cross_conversation_recall(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        engine = create_engine(f"sqlite:///{path}")
        Base.metadata.create_all(engine)
        Session = sessionmaker(bind=engine)
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
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
