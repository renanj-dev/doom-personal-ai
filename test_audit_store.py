import os
import tempfile
import unittest

from audit_store import ToolAuditRecord, ToolAuditStore


class AuditStoreTests(unittest.TestCase):
    def test_record_and_query(self):
        fd, path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        try:
            store = ToolAuditStore(f"sqlite:///{path}")
            store.init()
            row_id = store.record(
                session_id="s1",
                tool="calculator",
                action="invoke",
                permission="safe",
                ok=True,
                detail="ok",
            )
            self.assertGreater(row_id, 0)
            rows = store.recent(session_id="s1", limit=10)
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0].tool, "calculator")
            self.assertTrue(rows[0].ok)
            self.assertIsInstance(rows[0], ToolAuditRecord)
        finally:
            try:
                os.remove(path)
            except FileNotFoundError:
                pass


if __name__ == "__main__":
    unittest.main()
