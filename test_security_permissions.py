import os
import tempfile
import unittest

from security_permissions import (
    Decision,
    PermissionEngine,
    PermissionMode,
    PermissionScope,
    PermissionStore,
    SecureToolGate,
)


class PermissionEngineTests(unittest.TestCase):
    def setUp(self):
        fd, self.path = tempfile.mkstemp(suffix=".db")
        os.close(fd)
        self.store = PermissionStore(f"sqlite:///{self.path}")
        self.store.init()
        self.engine = PermissionEngine(self.store)

    def tearDown(self):
        try:
            os.remove(self.path)
        except FileNotFoundError:
            pass

    def test_default_safe(self):
        decision = self.engine.decide(
            tool_name="calculator", session_id="s1", default_mode=PermissionMode.SAFE
        )
        self.assertEqual(decision.decision, Decision.ALLOW)

    def test_global_blocked_overrides_safe_default(self):
        self.store.upsert_permission(
            tool_name="calculator", scope=PermissionScope.GLOBAL, mode=PermissionMode.BLOCKED
        )
        decision = self.engine.decide(
            tool_name="calculator", session_id="s1", default_mode=PermissionMode.SAFE
        )
        self.assertEqual(decision.decision, Decision.BLOCKED)
        self.assertEqual(decision.source_scope, PermissionScope.GLOBAL)

    def test_session_precedence_over_user_and_global(self):
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.GLOBAL, mode=PermissionMode.BLOCKED
        )
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.USER, scope_id="u1", mode=PermissionMode.CONFIRM
        )
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.SESSION, scope_id="s1", mode=PermissionMode.SAFE
        )
        decision = self.engine.decide(
            tool_name="demo", session_id="s1", user_id="u1", default_mode=PermissionMode.BLOCKED
        )
        self.assertEqual(decision.decision, Decision.ALLOW)
        self.assertEqual(decision.source_scope, PermissionScope.SESSION)

    def test_confirmation_is_bound_and_one_time(self):
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.GLOBAL, mode=PermissionMode.CONFIRM
        )
        decision = self.engine.decide(tool_name="demo", session_id="s1", user_id="u1")
        self.assertEqual(decision.decision, Decision.CONFIRM)

        token = self.engine.issue_confirmation(
            decision=decision, session_id="s1", user_id="u1", args={"x": 2}
        )
        first = self.engine.confirm_and_authorize(
            tool_name="demo", session_id="s1", user_id="u1", args={"x": 2}, confirmation_token=token
        )
        self.assertEqual(first.decision, Decision.ALLOW)

        second = self.engine.confirm_and_authorize(
            tool_name="demo", session_id="s1", user_id="u1", args={"x": 2}, confirmation_token=token
        )
        self.assertEqual(second.decision, Decision.BLOCKED)
        self.assertEqual(second.reason, "confirmation_already_used")

    def test_confirmation_rejects_argument_change(self):
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.GLOBAL, mode=PermissionMode.CONFIRM
        )
        decision = self.engine.decide(tool_name="demo", session_id="s1", user_id="u1")
        token = self.engine.issue_confirmation(
            decision=decision, session_id="s1", user_id="u1", args={"x": 2}
        )
        result = self.engine.confirm_and_authorize(
            tool_name="demo", session_id="s1", user_id="u1", args={"x": 3}, confirmation_token=token
        )
        self.assertEqual(result.decision, Decision.BLOCKED)
        self.assertEqual(result.reason, "arguments_mismatch")

    def test_disabled_policy_blocks(self):
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.GLOBAL, mode=PermissionMode.SAFE, enabled=False
        )
        result = self.engine.decide(tool_name="demo", session_id="s1")
        self.assertEqual(result.decision, Decision.BLOCKED)
        self.assertEqual(result.reason, "disabled_by_global_policy")

    def test_gate_issues_confirmation_without_execution(self):
        self.store.upsert_permission(
            tool_name="demo", scope=PermissionScope.GLOBAL, mode=PermissionMode.CONFIRM
        )
        gate = SecureToolGate(self.engine)
        payload = gate.authorize(
            tool_name="demo",
            session_id="s1",
            user_id="u1",
            args={"value": 7},
            default_mode=PermissionMode.BLOCKED,
            issue_confirmation=True,
        )
        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["decision"], "confirm")
        self.assertIn("confirmation_token", payload)


if __name__ == "__main__":
    unittest.main()
