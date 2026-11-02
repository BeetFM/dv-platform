import unittest
from copy import deepcopy
from dataclasses import replace
from unittest.mock import patch

from dv_platform.ai.model_client import AIPlanningError, LiteLLMModelClient, ModelRequest


class LiteLLMClientBranchTests(unittest.TestCase):
    def test_invalid_usage_counts_are_ignored_and_gateway_results_have_current_module_identity(self):
        import pickle

        from dv_platform.ai.gateway import GatewayResult
        from dv_platform.ai.model_client import _optional_int

        for value in (True, -1, float("inf"), float("nan"), 1.5):
            self.assertIsNone(_optional_int(value))
        value = GatewayResult("physical_design", "accepted", 1, "context", "prompt", None)
        self.assertEqual(pickle.loads(pickle.dumps(value)), value)

    @staticmethod
    def _request() -> ModelRequest:
        return ModelRequest("provider/model", "system", "user", {}, None, None, None, 1, 0, 16)

    def test_missing_dependency_is_categorized(self) -> None:
        with patch("dv_platform.ai.model_client.importlib.import_module", side_effect=ImportError):
            with self.assertRaisesRegex(AIPlanningError, "not installed"):
                LiteLLMModelClient().complete(self._request())

    def test_reasoning_models_do_not_receive_unsupported_sampling_parameters(self) -> None:
        for reasoning in (True, False, RuntimeError("capability unavailable")):
            calls = []

            class FakeLiteLLM:
                @staticmethod
                def supports_reasoning(*, model, _reasoning=reasoning):
                    if isinstance(_reasoning, Exception):
                        raise _reasoning
                    return _reasoning

                @staticmethod
                def completion(_calls=calls, **kwargs):
                    _calls.append(kwargs)
                    return {"choices": [{"message": {"content": "{}"}}]}

            with (
                self.subTest(reasoning=reasoning),
                patch("dv_platform.ai.model_client.importlib.import_module", return_value=FakeLiteLLM),
            ):
                request = replace(self._request(), model="openai/gpt-6-luna")
                LiteLLMModelClient().complete(request)
                self.assertEqual("temperature" in calls[0], reasoning is False)

    def test_provider_schema_adaptation_preserves_named_fields_and_local_validation_contract(self) -> None:
        from dv_platform.ai.model_client import _structured_output_schema

        schema = {
            "type": "object",
            "properties": {
                "uniqueItems": {"type": "boolean"},
                "values": {
                    "type": "array",
                    "uniqueItems": True,
                    "items": {
                        "anyOf": [{"type": "array", "uniqueItems": True, "items": {"type": "string"}}, {"type": "null"}]
                    },
                },
                "fixed": {"const": {"uniqueItems": "data, not a schema keyword"}},
            },
        }
        original = deepcopy(schema)
        adapted = _structured_output_schema(schema)
        self.assertEqual(schema, original)
        self.assertIn("uniqueItems", adapted["properties"])
        self.assertNotIn("uniqueItems", adapted["properties"]["values"])
        self.assertNotIn("uniqueItems", adapted["properties"]["values"]["items"]["anyOf"][0])
        self.assertEqual(adapted["properties"]["fixed"], original["properties"]["fixed"])

    def test_provider_error_categories(self) -> None:
        errors = (
            (TimeoutError("late"), "timeout"),
            (RuntimeError("unauthorized"), "authentication_failed"),
            (RuntimeError("too many requests"), "rate_limited"),
            (RuntimeError("broken"), "provider_error"),
        )
        for error, category in errors:

            class FakeLiteLLM:
                @staticmethod
                def completion(_error=error, **_kwargs):
                    raise _error

            with (
                self.subTest(category=category),
                patch("dv_platform.ai.model_client.importlib.import_module", return_value=FakeLiteLLM),
            ):
                with self.assertRaises(AIPlanningError) as raised:
                    LiteLLMModelClient().complete(self._request())
                self.assertEqual(raised.exception.category, category)

    def test_content_parts_usage_conversion_and_cost_failures(self) -> None:
        class FakeLiteLLM:
            @staticmethod
            def supports_response_schema(*, model):
                raise RuntimeError(model)

            @staticmethod
            def completion(**_kwargs):
                return {
                    "choices": [{"message": {"content": [{"text": "{"}, {"ignored": True}, {"text": "}"}]}}],
                    "usage": {"prompt_tokens": "2", "completion_tokens": b"3", "total_tokens": "bad"},
                    "retry_count": 1.9,
                }

            @staticmethod
            def completion_cost(**_kwargs):
                raise RuntimeError("cost unavailable")

        with patch("dv_platform.ai.model_client.importlib.import_module", return_value=FakeLiteLLM):
            response = LiteLLMModelClient().complete(self._request())

        self.assertEqual(response.content, "{}")
        self.assertEqual((response.prompt_tokens, response.completion_tokens), (2, 3))
        self.assertIsNone(response.total_tokens)
        self.assertEqual(response.retry_count, 0)
        self.assertIsNone(response.cost)
        self.assertFalse(response.structured_output)

    def test_missing_choices_and_non_text_content_are_rejected(self) -> None:
        responses = ({}, {"choices": []}, {"choices": [{"message": {"content": []}}]})
        for provider_response in responses:

            class FakeLiteLLM:
                @staticmethod
                def completion(_response=provider_response, **_kwargs):
                    return _response

            with (
                self.subTest(response=provider_response),
                patch("dv_platform.ai.model_client.importlib.import_module", return_value=FakeLiteLLM),
            ):
                with self.assertRaises(AIPlanningError):
                    LiteLLMModelClient().complete(self._request())
