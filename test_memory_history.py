from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from memory_history_engine import (
    Conversation,
    Memory,
    MemoryCategory,
    MemoryHistoryService,
    MemoryHistoryStore,
    MemoryPatch,
    Message,
    MutationStatus,
)
from sqlalchemy import select


class MemoryHistoryTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        db_url = f"sqlite:///{Path(self.tmp.name) / 'doom.db'}"
        self.store = MemoryHistoryStore(db_url)
        self.store.init()
        with self.store.SessionLocal() as db:
            conv = Conversation(session_id="sess-1", title="Teste")
            conv.messages = [
                Message(role="user", content="Olá"),
                Message(role="assistant", content="Olá, Renan."),
            ]
            db.add(conv)
            db.add(Memory(user_id="renan", category=MemoryCategory.PROJECT.value, content="Doom é meu projeto."))
            db.commit()

    def tearDown(self):
        self.store.close()
        self.tmp.cleanup()

    def test_delete_history_removes_messages_and_conversation(self):
        result = self.store.delete_conversation("sess-1")
        self.assertTrue(result.ok)
        self.assertEqual(result.deleted_messages, 2)
        self.assertIsNone(self.store.get_conversation("sess-1"))
        with self.store.SessionLocal() as db:
            self.assertEqual(len(list(db.scalars(select(Message)).all())), 0)

    def test_delete_history_does_not_delete_memory(self):
        result = self.store.delete_conversation("sess-1")
        self.assertTrue(result.ok)
        memories = self.store.list_memories(user_id="renan")
        self.assertEqual(len(memories), 1)
        self.assertEqual(memories[0].content, "Doom é meu projeto.")

    def test_edit_memory_persists_content_and_returns_saved_state(self):
        memory = self.store.list_memories(user_id="renan")[0]
        result = self.store.update_memory(
            memory.id,
            MemoryPatch(content="Doom é meu projeto pessoal de IA.", category=MemoryCategory.PROJECT.value, expected_revision=memory.revision),
            user_id="renan",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["content"], "Doom é meu projeto pessoal de IA.")
        self.assertEqual(result.data["revision"], 2)
        fresh = self.store.get_memory(memory.id, user_id="renan")
        self.assertEqual(fresh.content, "Doom é meu projeto pessoal de IA.")

    def test_blank_memory_edit_is_rejected(self):
        memory = self.store.list_memories(user_id="renan")[0]
        result = self.store.update_memory(memory.id, MemoryPatch(content="   "), user_id="renan")
        self.assertEqual(result.status, MutationStatus.INVALID)

    def test_stale_memory_revision_is_rejected(self):
        memory = self.store.list_memories(user_id="renan")[0]
        first = self.store.update_memory(memory.id, MemoryPatch(content="Versão 2", expected_revision=1), user_id="renan")
        self.assertTrue(first.ok)
        stale = self.store.update_memory(memory.id, MemoryPatch(content="Versão antiga", expected_revision=1), user_id="renan")
        self.assertEqual(stale.status, MutationStatus.CONFLICT)
        self.assertEqual(stale.data["current_revision"], 2)

    def test_service_requires_confirmation_when_security_denies_until_token(self):
        calls = []
        def authorize(**kwargs):
            calls.append(kwargs)
            if kwargs.get("confirmation_token") == "ok":
                return {"allowed": True, "decision": "allow", "reason": "confirmation_consumed"}
            return {"allowed": False, "decision": "confirm", "reason": "confirmation_required"}

        service = MemoryHistoryService(self.store, authorize=authorize)
        memory = self.store.list_memories(user_id="renan")[0]
        result = service.edit_memory(
            memory_id=memory.id,
            session_id="sess-1",
            patch=MemoryPatch(content="Com confirmação"),
            user_id="renan",
        )
        self.assertEqual(result.status, MutationStatus.INVALID)
        result = service.edit_memory(
            memory_id=memory.id,
            session_id="sess-1",
            patch=MemoryPatch(content="Com confirmação"),
            user_id="renan",
            confirmation_token="ok",
        )
        self.assertTrue(result.ok)
        self.assertEqual(result.data["content"], "Com confirmação")
        self.assertEqual(len(calls), 2)

    def test_service_writes_audit_without_memory_content(self):
        events = []
        service = MemoryHistoryService(self.store, audit=lambda **kwargs: events.append(kwargs))
        memory = self.store.list_memories(user_id="renan")[0]
        result = service.edit_memory(
            memory_id=memory.id,
            session_id="sess-1",
            patch=MemoryPatch(content="Segredo que não deve ir para auditoria"),
            user_id="renan",
        )
        self.assertTrue(result.ok)
        serialized = str(events)
        self.assertNotIn("Segredo que não deve ir para auditoria", serialized)
        self.assertEqual(events[0]["metadata"]["memory_id"], memory.id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
