import json
import unittest
from unittest.mock import patch

from dv_platform.ai.model_client import LiteLLMModelClient, ModelRequest, ai_dependency_available


@unittest.skipUnless(ai_dependency_available(), "install dv-platform[ai] for the real LiteLLM transport check")
class LiteLLMTransportTests(unittest.TestCase):
    def test_responses_model_keeps_structured_output_and_reasoning_without_function_tools(self):
        import httpx
        import litellm
        from litellm.llms.custom_httpx.http_handler import HTTPHandler

        attempts = []

        def handle(request):
            self.assertEqual(request.url.path, "/v1/responses")
            attempts.append(json.loads(request.content))
            return httpx.Response(
                200,
                json={
                    "id": "resp_fixture",
                    "object": "response",
                    "created_at": 1,
                    "status": "completed",
                    "model": "gpt-6-luna",
                    "output": [
                        {
                            "id": "msg_fixture",
                            "type": "message",
                            "role": "assistant",
                            "status": "completed",
                            "content": [{"type": "output_text", "text": '{"ok":true}', "annotations": []}],
                        }
                    ],
                    "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
                },
            )

        transport = httpx.Client(transport=httpx.MockTransport(handle))
        sdk = HTTPHandler(client=transport)
        original = litellm.completion
        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }
        request = ModelRequest(
            "openai/responses/gpt-6-luna",
            "Return JSON.",
            "Return ok true.",
            schema,
            "fixture-key",
            "https://openai.invalid/v1",
            None,
            5,
            0,
            100,
        )
        with (
            transport,
            patch.object(litellm, "completion", side_effect=lambda **kwargs: original(**kwargs, client=sdk)),
        ):
            response = LiteLLMModelClient().complete(request)
        self.assertEqual(json.loads(response.content), {"ok": True})
        self.assertTrue(response.structured_output)
        self.assertEqual(attempts[0]["text"]["format"]["type"], "json_schema")
        self.assertNotIn("tools", attempts[0])
        self.assertNotIn("temperature", attempts[0])

    def test_throttled_provider_retries_through_real_sdk_without_network(self):
        import httpx
        import litellm
        from openai import OpenAI

        attempts = []

        def handle(request):
            attempts.append(json.loads(request.content))
            if len(attempts) == 1:
                return httpx.Response(
                    429,
                    json={
                        "error": {"message": "retry fixture", "type": "rate_limit_error", "code": "rate_limit_exceeded"}
                    },
                )
            return httpx.Response(
                200,
                json={
                    "id": "fixture",
                    "object": "chat.completion",
                    "created": 1,
                    "model": "gpt-6-luna",
                    "choices": [
                        {
                            "index": 0,
                            "message": {"role": "assistant", "content": '{"ok":true}'},
                            "finish_reason": "stop",
                        }
                    ],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                },
            )

        sdk = OpenAI(
            api_key="fixture-key",
            base_url="https://openai.invalid/v1",
            max_retries=0,
            http_client=httpx.Client(transport=httpx.MockTransport(handle)),
        )
        original = litellm.completion

        def complete(**kwargs):
            return original(**kwargs, client=sdk)

        schema = {
            "type": "object",
            "additionalProperties": False,
            "required": ["ok"],
            "properties": {"ok": {"type": "boolean"}},
        }
        request = ModelRequest(
            "openai/gpt-6-luna",
            "Return JSON.",
            "Return ok true.",
            schema,
            "fixture-key",
            "https://openai.invalid/v1",
            None,
            5,
            1,
            100,
        )
        with sdk, patch.object(litellm, "completion", side_effect=complete):
            response = LiteLLMModelClient().complete(request)
        self.assertEqual(len(attempts), 2)
        self.assertEqual(json.loads(response.content), {"ok": True})
        self.assertTrue(response.structured_output)
        self.assertNotIn("temperature", attempts[0])
