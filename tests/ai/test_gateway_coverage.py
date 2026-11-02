import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import Mock, patch

from dv_platform.ai.gateway import LiteLLMGateway, _endpoint_identity
from dv_platform.ai.model_client import AIPlanningError, ModelResponse
from dv_platform.ai.optimization import OptimizationMetrics
from dv_platform.core.config import default_config
from dv_platform.domain.models import AIConfig


class GatewayCoverageTests(unittest.TestCase):
    def test_denied_stage_missing_model_and_missing_credential_never_contact_provider(self):
        with TemporaryDirectory() as directory:
            for ai, reason in (
                (AIConfig(model="fixture/model", allowed_stages=("feedback_analysis",)), "stage_not_allowed"),
                (AIConfig(), "model_not_configured"),
                (AIConfig(model="fixture/model", api_key_env="MISSING_TEST_CREDENTIAL"), "credential_missing"),
            ):
                config = replace(default_config(Path(directory)), allow_network=True, ai=ai)
                client = Mock()
                with self.subTest(reason=reason), patch.dict("os.environ", {"MISSING_TEST_CREDENTIAL": ""}):
                    result = self.execute(config, client)
                self.assertEqual(result.fallback_reason, reason)
                self.assertEqual(result.attempts, 0)
                client.complete.assert_not_called()

    @staticmethod
    def execute(config, client, validate=None):
        return LiteLLMGateway(config, client).execute(
            stage="physical_design",
            system_prompt="system",
            user_prompt="user",
            response_schema={},
            context="evidence",
            validate=validate,
        )

    def test_retry_receipts_hash_the_actual_last_request(self):
        import hashlib
        import json

        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), allow_network=True, ai=AIConfig(model="fixture/model"))
            for accept_second in (True, False):
                client = Mock()
                client.complete.return_value = ModelResponse("{}")
                calls = []

                def validate(raw, calls=calls, accept_second=accept_second):
                    calls.append(raw)
                    if not accept_second or len(calls) == 1:
                        raise ValueError("correct the fixture response")

                result = self.execute(config, client, validate)
                request = client.complete.call_args.args[0]
                expected = hashlib.sha256((request.system_prompt + "\n" + request.user_prompt).encode()).hexdigest()
                self.assertEqual(result.prompt_hash, expected)
                self.assertEqual(json.loads(result.run_record_path.read_text())["prompt_hash"], expected)
                self.assertEqual(result.status, "accepted" if accept_second else "fallback")

    def test_ci_optimizer_error_stops_before_a_model_call(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)), allow_network=True, ci=True, ai=AIConfig(model="fixture/model")
            )
            client = Mock()
            metrics = (OptimizationMetrics("physical_design", "headroom", "failed"),)
            with patch("dv_platform.ai.gateway.optimize_model_prompt", return_value=("optimized", metrics)):
                result = self.execute(config, client)
            self.assertEqual(result.fallback_reason, "headroom_optimization_failed")
            client.complete.assert_not_called()

    def test_invalid_provider_responses_are_repaired_but_authentication_errors_are_terminal(self):
        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), allow_network=True, ai=AIConfig(model="fixture/model"))
            client = Mock()
            client.complete.side_effect = [AIPlanningError("invalid_response", "missing content"), ModelResponse("{}")]
            result = self.execute(config, client)
            self.assertEqual(result.status, "accepted")
            self.assertEqual(result.attempts, 2)
            client.complete.side_effect = AIPlanningError("authentication_failed", "fixture rejected")
            result = self.execute(config, client)
            self.assertEqual(result.fallback_reason, "authentication_failed")
            self.assertEqual(result.attempts, 1)

    def test_repeated_invalid_output_exhausts_the_bounded_repair_budget(self):
        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), allow_network=True, ai=AIConfig(model="fixture/model"))
            client = Mock()
            client.complete.side_effect = AIPlanningError("invalid_response", "missing content")
            result = self.execute(config, client)
            self.assertEqual(result.fallback_reason, "repair_attempts_exhausted")
            self.assertEqual(result.attempts, 3)
            self.assertEqual(client.complete.call_count, 3)

    def test_ci_optimizer_failure_and_non_headroom_metrics_are_distinct(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), ci=True)
            gateway = LiteLLMGateway(config)
            failed = OptimizationMetrics("physical_design", "headroom", "failed")
            fallback = gateway._optimizer_fallback("physical_design", "context", "prompt", (failed,))
            self.assertIsNotNone(fallback)
            assert fallback is not None
            self.assertEqual(fallback.fallback_reason, "headroom_optimization_failed")

            compressed = OptimizationMetrics("physical_design", "headroom", "compressed")
            unrelated = OptimizationMetrics("physical_design", "code_review_graph", "unavailable")
            self.assertIsNone(
                gateway._optimizer_fallback("physical_design", "context", "prompt", (compressed, unrelated))
            )
            self.assertIsNone(
                LiteLLMGateway(replace(config, ci=False))._optimizer_fallback(
                    "physical_design", "context", "prompt", (failed,)
                )
            )

    def test_endpoint_identity_normalizes_port_and_empty_values(self) -> None:
        self.assertIsNone(_endpoint_identity(None))
        self.assertEqual(
            _endpoint_identity("HTTPS://user:secret@Example.TEST:8443/v1/?token=secret"),
            "https://example.test:8443/v1",
        )


if __name__ == "__main__":
    unittest.main()
