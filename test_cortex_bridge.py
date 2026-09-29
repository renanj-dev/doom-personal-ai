import unittest

from doom_tools import CortexToolBridge, Permission, ToolSpec, build_default_engine


class CortexBridgeTests(unittest.TestCase):
    def setUp(self):
        self.engine = build_default_engine()
        self.bridge = CortexToolBridge(self.engine)

    def test_build_catalog_contains_tools(self):
        names = {item["name"] for item in self.bridge.catalog()}
        self.assertIn("calculator", names)

    def test_parse_exact_json_request(self):
        req = self.bridge.parse_request('{"tool":"calculator","args":{"expression":"2+2"}}')
        self.assertIsNotNone(req)
        self.assertEqual(req.tool, "calculator")
        self.assertEqual(req.args["expression"], "2+2")

    def test_does_not_extract_json_from_prose(self):
        self.assertIsNone(self.bridge.parse_request('Use this: {"tool":"calculator","args":{"expression":"2+2"}} agora.'))

    def test_handle_safe_tool(self):
        out = self.bridge.handle_model_output(
            '{"tool":"calculator","args":{"expression":"5*6"}}',
            session_id="s1",
        )
        self.assertEqual(out.kind, "tool_result")
        self.assertTrue(out.result.ok)
        self.assertEqual(out.result.data["result"], 30)

    def test_confirmation_passthrough(self):
        self.engine.register(ToolSpec(
            name="demo_confirm",
            description="test",
            permission=Permission.CONFIRM,
            handler=lambda value: {"value": value},
            parameters={"value": "string"},
        ))
        out = self.bridge.handle_model_output(
            '{"tool":"demo_confirm","args":{"value":"abc"}}',
            session_id="s2",
        )
        self.assertEqual(out.kind, "confirmation")
        self.assertTrue(out.result.confirmation_token)

    def test_run_loop_returns_model_final_answer_after_tool(self):
        replies = iter([
            '{"tool":"calculator","args":{"expression":"7*6"}}',
            "O resultado é 42.",
        ])
        prompts = []

        def ask_model(prompt: str) -> str:
            prompts.append(prompt)
            return next(replies)

        final, events = self.bridge.run_loop(
            user_message="Quanto é 7 vezes 6?",
            session_id="s3",
            ask_model=ask_model,
        )
        self.assertEqual(final, "O resultado é 42.")
        self.assertEqual([e.kind for e in events], ["tool_result", "text"])
        self.assertIn("DOOM_TOOL_RESULT", prompts[1])
        self.assertIn('"result":42', prompts[1])


if __name__ == "__main__":
    unittest.main()
