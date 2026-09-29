import unittest
from doom_tools import Permission, build_default_engine


class ToolEngineTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_default_engine()

    def test_safe_calculator(self):
        result = self.engine.invoke("calculator", {"expression": "2 + 3 * 4"}, session_id="test")
        self.assertTrue(result.ok)
        self.assertEqual(result.data["result"], 14)

    def test_blocks_unsafe_expression(self):
        result = self.engine.invoke("calculator", {"expression": "__import__('os').system('whoami')"}, session_id="test")
        self.assertFalse(result.ok)

    def test_confirmation_flow(self):
        # Register a temporary confirmation-required tool.
        self.engine.register(__import__('doom_tools').ToolSpec(
            name="demo_confirm",
            description="test",
            permission=Permission.CONFIRM,
            handler=lambda value: {"value": value},
            parameters={"value": "string"},
        ))
        first = self.engine.invoke("demo_confirm", {"value": "ok"}, session_id="test")
        self.assertFalse(first.ok)
        self.assertTrue(first.confirmation_token)
        second = self.engine.invoke("demo_confirm", {"value": "ok"}, session_id="test", confirmation_token=first.confirmation_token)
        self.assertTrue(second.ok)
        self.assertEqual(second.data["value"], "ok")


if __name__ == "__main__":
    unittest.main()
