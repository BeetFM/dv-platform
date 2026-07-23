"""Opt-in live provider smoke coverage; never enabled by the standard test run."""

import json
import os
import unittest

from dv_platform.analysis.ai_planning import LiteLLMModelClient, ModelRequest, proposal_json_schema


class AIProviderSmokeTests(unittest.TestCase):
    def test_configured_live_providers_return_json(self) -> None:
        if os.environ.get("DV_PLATFORM_AI_SMOKE") != "1":
            self.skipTest("set DV_PLATFORM_AI_SMOKE=1 to enable live AI provider smoke tests")
        providers = (
            ("OPENAI", "OPENAI_API_KEY"),
            ("ANTHROPIC", "ANTHROPIC_API_KEY"),
            ("GEMINI", "GEMINI_API_KEY"),
            ("DEEPSEEK", "DEEPSEEK_API_KEY"),
            ("MOONSHOT", "MOONSHOT_API_KEY"),
            ("OLLAMA", None),
        )
        configured = tuple(
            (name, os.environ[f"DV_PLATFORM_AI_SMOKE_{name}_MODEL"], key_env)
            for name, key_env in providers
            if os.environ.get(f"DV_PLATFORM_AI_SMOKE_{name}_MODEL")
        )
        if not configured:
            self.skipTest("no DV_PLATFORM_AI_SMOKE_<PROVIDER>_MODEL variables are configured")

        client = LiteLLMModelClient()
        for name, model, key_env in configured:
            with self.subTest(provider=name):
                response = client.complete(
                    ModelRequest(
                        model=model,
                        system_prompt="Return JSON only. Do not call tools.",
                        user_prompt=(
                            '{"schema_version":1,"module":"smoke","requirements":[],"checks":[],'
                            '"assumptions":[],"open_questions":[]}'
                        ),
                        response_schema=proposal_json_schema(),
                        api_key=os.environ.get(key_env) if key_env else None,
                        api_base=os.environ.get(f"DV_PLATFORM_AI_SMOKE_{name}_API_BASE"),
                        api_version=os.environ.get(f"DV_PLATFORM_AI_SMOKE_{name}_API_VERSION"),
                        timeout_seconds=60,
                        max_retries=1,
                        max_output_tokens=256,
                    )
                )
                self.assertIsInstance(json.loads(response.content), dict)


if __name__ == "__main__":
    unittest.main()
