import unittest

from dv_platform.core.config import validate_ai_config
from dv_platform.core.models import AIConfig


class AIConfigurationBranchTests(unittest.TestCase):
    def test_valid_boundary_values(self) -> None:
        for config in (
            AIConfig(
                model="m",
                api_base="http://localhost:1/path?ordinary=value",
                timeout_seconds=1.0,
                max_retries=0,
                max_output_tokens=1,
                max_context_chars=1024,
                allowed_stages=("physical_design",),
                max_repair_attempts=0,
            ),
            AIConfig(
                model="m" * 512,
                api_base="https://example.test:65535/v1",
                api_key_env="_TOKEN_1",
                api_version="v1",
                timeout_seconds=600.0,
                max_retries=10,
                max_output_tokens=65536,
                max_context_chars=1_000_000,
                max_repair_attempts=2,
            ),
        ):
            with self.subTest(config=config):
                self.assertEqual(validate_ai_config(config), ())

        self.assertEqual(validate_ai_config(AIConfig(), require_model=False), ())

    def test_scalar_and_collection_bounds_are_rejected(self) -> None:
        invalid = {
            "model blank": AIConfig(),
            "model surrounding whitespace": AIConfig(model=" model"),
            "model length": AIConfig(model="m" * 513),
            "model control": AIConfig(model="bad\nmodel"),
            "key syntax": AIConfig(model="m", api_key_env="1-BAD"),
            "key length": AIConfig(model="m", api_key_env="A" * 129),
            "version whitespace": AIConfig(model="m", api_version=" v1"),
            "version length": AIConfig(model="m", api_version="v" * 129),
            "version control": AIConfig(model="m", api_version="v1\n"),
            "timeout low": AIConfig(model="m", timeout_seconds=0.99),
            "timeout high": AIConfig(model="m", timeout_seconds=600.01),
            "retries low": AIConfig(model="m", max_retries=-1),
            "retries high": AIConfig(model="m", max_retries=11),
            "tokens low": AIConfig(model="m", max_output_tokens=0),
            "tokens high": AIConfig(model="m", max_output_tokens=65537),
            "context low": AIConfig(model="m", max_context_chars=1023),
            "context high": AIConfig(model="m", max_context_chars=1_000_001),
            "stages empty": AIConfig(model="m", allowed_stages=()),
            "stages duplicate": AIConfig(model="m", allowed_stages=("physical_design", "physical_design")),
            "stage unknown": AIConfig(model="m", allowed_stages=("publishing",)),
            "repairs low": AIConfig(model="m", max_repair_attempts=-1),
            "repairs high": AIConfig(model="m", max_repair_attempts=3),
            "fallback": AIConfig(model="m", fallback="another-provider"),
        }
        for label, config in invalid.items():
            with self.subTest(label=label):
                diagnostics = validate_ai_config(config)
                self.assertTrue(diagnostics)
                self.assertTrue(all(item.severity == "error" for item in diagnostics))

    def test_endpoint_security_matrix(self) -> None:
        invalid_endpoints = (
            "ftp://example.test/v1",
            "/relative/v1",
            "https://example.test:bad/v1",
            "https://example.test:70000/v1",
            "https://user@example.test/v1",
            "https://user:password@example.test/v1",
            "https://example.test/v1?token=secret",
            "https://example.test/v1?API-KEY=secret",
            "https://example.test/v1#fragment",
            " https://example.test/v1",
            "https://example.test/" + "x" * 2048,
            "https://example.test/v1\n",
        )
        for endpoint in invalid_endpoints:
            with self.subTest(endpoint=endpoint[:80]):
                self.assertTrue(validate_ai_config(AIConfig(model="m", api_base=endpoint)))
