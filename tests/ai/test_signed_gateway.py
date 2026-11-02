import base64
import json
import os
import subprocess
from copy import deepcopy
from dataclasses import replace
from hashlib import sha256
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.model_client import AIPlanningError, ModelResponse
from dv_platform.ai.optimization import OptimizationMetrics
from dv_platform.core.config import default_config
from dv_platform.domain.models import AIConfig
from dv_platform.signing import canonical_signed_document, verify_signed_document
from tests.ai.test_routing_policy import _Client, _document
from tests.support.entitlements import issue_test_entitlement


class SignedGatewayTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        product = issue_test_entitlement(self.root, ("cli.enterprise", "ai.provider.anthropic"))
        self.certificate = self.root / "fixture-entitlement/issuer-certificate.pem"
        self.key = self.root / "fixture-entitlement/issuer-key.pem"
        self.path = self.root / "routing.json"
        self.document = _document()
        payload = self.root / "payload.json"
        payload.write_bytes(canonical_signed_document(self.document))
        detached = self.root / "signature.der"
        subprocess.run(
            ("openssl", "dgst", "-sha256", "-sign", str(self.key), "-out", str(detached), str(payload)),
            check=True,
            capture_output=True,
            timeout=10,
        )
        self.document["signature"] = {
            "certificate_file": str(self.certificate.relative_to(self.root)),
            "certificate_sha256": sha256(self.certificate.read_bytes()).hexdigest(),
            "value": base64.b64encode(detached.read_bytes()).decode(),
        }
        self.path.write_text(json.dumps(self.document))
        self.config = replace(
            default_config(self.root),
            allow_network=True,
            product=product,
            ai=AIConfig(
                model="fixture/default",
                routing_policy_path=self.path,
                routing_trust_root=self.certificate,
                destination="external-us",
            ),
        )

    def execute(self, client, *, config=None, validate=json.loads):
        with patch.dict(os.environ, {"OPENAI_API_KEY": "fixture-openai", "ANTHROPIC_API_KEY": "fixture-anthropic"}):
            return LiteLLMGateway(config or self.config, client).execute(
                stage="physical_design",
                system_prompt="system",
                user_prompt="context",
                response_schema={},
                context="measured evidence",
                validate=validate,
            )

    def test_real_p256_signature_allows_audited_route_without_persisting_credentials(self):
        client = _Client(ModelResponse("{}", cost=0.1, total_tokens=12))
        result = self.execute(client)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(client.requests[0].model, self.document["cells"][0]["model_snapshot"])
        receipt = result.run_record_path.read_text()
        self.assertNotIn("fixture-openai", receipt)
        self.assertNotIn("fixture-anthropic", receipt)
        self.assertEqual(json.loads(receipt)["routing_attempts"][0]["status"], "accepted")

    def test_ci_headroom_failure_stops_signed_routes_before_model_calls(self):
        client = _Client(ModelResponse("{}", cost=0.1))
        metrics = (OptimizationMetrics("physical_design", "headroom", "anchor_removed"),)
        with patch("dv_platform.ai.gateway.optimize_model_prompt", return_value=("context", metrics)):
            result = self.execute(client, config=replace(self.config, ci=True))
        self.assertEqual(result.fallback_reason, "headroom_optimization_failed")
        self.assertEqual(client.requests, [])

    def test_tampered_policy_is_rejected_before_any_model_call(self):
        self.document["cells"][0]["region"] = "elsewhere"
        self.path.write_text(json.dumps(self.document))
        client = _Client(ModelResponse("{}", cost=0.1))
        result = self.execute(client)
        self.assertEqual(result.fallback_reason, "routing_policy_invalid")
        self.assertEqual(result.attempts, 0)
        self.assertEqual(client.requests, [])

    def test_route_without_optional_validator_is_audited(self):
        result = self.execute(_Client(ModelResponse("{}", cost=0.1)), validate=None)
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.attempts, 1)

    def test_routed_context_failure_never_calls_the_provider(self):
        client = _Client(ModelResponse("{}", cost=0.1))
        with patch(
            "dv_platform.ai.gateway.optimize_model_prompt", side_effect=AIPlanningError("context_budget", "fixture")
        ):
            result = self.execute(client)
        self.assertEqual(result.fallback_reason, "context_budget")
        self.assertEqual(result.attempts, 0)
        self.assertEqual(client.requests, [])

    def test_incomplete_or_missing_policy_never_calls_model(self):
        client = _Client(ModelResponse("{}", cost=0.1))
        config = replace(self.config, ai=replace(self.config.ai, routing_trust_root=None))
        self.assertEqual(self.execute(client, config=config).fallback_reason, "routing_policy_incomplete")
        self.path.unlink()
        self.assertEqual(self.execute(client).fallback_reason, "routing_policy_invalid")
        self.path.write_text("[]")
        self.assertEqual(self.execute(client).fallback_reason, "routing_policy_invalid")
        self.assertEqual(client.requests, [])

    def test_restricted_data_has_no_eligible_external_route(self):
        client = _Client(ModelResponse("{}", cost=0.1))
        config = replace(self.config, ai=replace(self.config.ai, data_class="restricted"))
        result = self.execute(client, config=config)
        self.assertEqual(result.fallback_reason, "provider_unavailable")
        self.assertEqual(result.attempts, 0)
        self.assertEqual(client.requests, [])

    def test_licensed_bootstrap_plan_is_honored_by_provider_routing(self):
        from dv_platform.domain.models import ProductConfig
        from dv_platform.product import resolve_configured_product_plan

        plan = resolve_configured_product_plan(self.config)
        config = replace(self.config, product=ProductConfig())
        client = _Client(ModelResponse("{}", cost=0.1))
        with (
            patch("dv_platform.ai.gateway.active_product_plan", return_value=plan),
            patch(
                "dv_platform.ai.gateway.resolve_secret",
                side_effect=lambda _config, name: "fixture" if name == "ANTHROPIC_API_KEY" else None,
            ),
        ):
            result = self.execute(client, config=config)
        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(result.status, "accepted")
        self.assertEqual(result.attempts, 1)

    def test_authentication_failure_is_an_attempted_call_and_never_crosses_providers(self):
        client = _Client(AIPlanningError("authentication_failed", "rejected fixture credential"))
        result = self.execute(client)
        self.assertEqual(result.fallback_reason, "authentication_failed")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result.attempts, 1)
        self.assertEqual(result.routing_attempts[0].status, "failed")

    def test_availability_failures_retain_actual_attempt_counts(self):
        client = _Client(AIPlanningError("timeout", "late"))
        result = self.execute(client)
        self.assertEqual(result.fallback_reason, "provider_unavailable")
        self.assertEqual(len(client.requests), 2)
        self.assertEqual(result.attempts, 2)

    def test_skipped_route_is_not_counted_as_a_model_call(self):
        client = _Client(ModelResponse("{}", cost=0.1))
        with patch(
            "dv_platform.ai.gateway.resolve_secret",
            side_effect=lambda _config, name: "fixture" if name == "ANTHROPIC_API_KEY" else None,
        ):
            result = self.execute(client)
        self.assertEqual(result.provider, "anthropic")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result.attempts, 1)
        self.assertEqual([item.status for item in result.routing_attempts], ["skipped", "accepted"])

    def test_nonfinite_and_negative_cost_evidence_is_rejected(self):
        for cost in (float("inf"), float("nan"), -0.1):
            with self.subTest(cost=cost):
                client = _Client(ModelResponse("{}", cost=cost))
                result = self.execute(client)
                self.assertEqual(result.fallback_reason, "cost_policy")
                self.assertEqual(result.attempts, 1)

    def test_unbounded_cost_is_rejected_and_counted_as_a_model_call(self):
        client = _Client(ModelResponse("{}"))
        result = self.execute(client)
        self.assertEqual(result.fallback_reason, "cost_policy")
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(result.attempts, 1)

    def test_invalid_response_is_not_misreported_as_an_invalid_signed_policy(self):
        client = _Client(ModelResponse("invalid JSON", cost=0.1))
        result = self.execute(client)
        self.assertEqual(result.fallback_reason, "invalid_response")
        self.assertEqual(result.attempts, 1)
        self.assertIsNone(result.proposal_hash)

    def test_signatures_reject_malformed_metadata_certificate_escape_and_invalid_encoding(self):
        self.assertTrue(verify_signed_document(self.document, self.path, self.certificate))
        for invalid in (
            None,
            {},
            {**self.document["signature"], "extra": True},
            {**self.document["signature"], "certificate_file": "../escape.pem"},
            {**self.document["signature"], "certificate_sha256": "0" * 64},
            {**self.document["signature"], "value": "not base64!"},
            {**self.document["signature"], "value": None},
        ):
            document = {**self.document, "signature": invalid}
            with self.subTest(signature=invalid):
                self.assertFalse(verify_signed_document(document, self.path, self.certificate))
        tampered = deepcopy(self.document)
        tampered["policy_version"] = "tampered"
        self.assertFalse(verify_signed_document(tampered, self.path, self.certificate))
        with patch("dv_platform.signing.which", return_value=None):
            self.assertFalse(verify_signed_document(self.document, self.path, self.certificate))
