import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.ai.gateway import LiteLLMGateway, _endpoint_identity
from dv_platform.ai.optimization import OptimizationMetrics
from dv_platform.core.config import default_config


class GatewayCoverageTests(unittest.TestCase):
    def test_ci_optimizer_failure_and_non_headroom_metrics_are_distinct(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), ci=True)
            gateway = LiteLLMGateway(config)
            failed = OptimizationMetrics("planning", "headroom", "failed")
            fallback = gateway._optimizer_fallback("planning", "context", "prompt", (failed,))
            self.assertIsNotNone(fallback)
            assert fallback is not None
            self.assertEqual(fallback.fallback_reason, "headroom_optimization_failed")

            compressed = OptimizationMetrics("planning", "headroom", "compressed")
            unrelated = OptimizationMetrics("planning", "tokensave", "unavailable")
            self.assertIsNone(gateway._optimizer_fallback("planning", "context", "prompt", (compressed, unrelated)))
            self.assertIsNone(
                LiteLLMGateway(replace(config, ci=False))._optimizer_fallback(
                    "planning", "context", "prompt", (failed,)
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
