import unittest

from dv_platform.ai.model_client import AIPlanningError, ModelRequest, ModelResponse
from dv_platform.ai.routing import DataClass, PolicyRouter, load_routing_policy
from dv_platform.product import FREE_CAPABILITIES, ResolvedProductPlan


class _Client:
    def __init__(self, outcome):
        self.outcome = outcome
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        if isinstance(self.outcome, Exception):
            raise self.outcome
        return self.outcome


def _document(*, moonshot_enabled: bool = False):
    cells = []
    identities = (
        ("openai", "openai/gpt-5.2-2026-06-01", "OPENAI_API_KEY", True),
        ("anthropic", "anthropic/claude-sonnet-4-20260601", "ANTHROPIC_API_KEY", True),
        ("moonshot", "moonshot/kimi-k3-account-cell-202607", "MOONSHOT_API_KEY", moonshot_enabled),
    )
    for provider, model, credential, enabled in identities:
        cells.append(
            {
                "provider": provider,
                "model_snapshot": model,
                "endpoint": f"https://{provider}.invalid/v1",
                "destination": "external-us",
                "region": "us",
                "credential_env": credential,
                "allowed_data_classes": ["public", "internal"],
                "allowed_purposes": ["planning"],
                "retention": "zero",
                "per_request_cost_limit": 1.0,
                "daily_cost_limit": 10.0,
                "enabled": enabled,
            }
        )
    return {
        "schema_version": 1,
        "policy_version": "routing-test-v1",
        "order": ["openai", "anthropic", "moonshot"],
        "cells": cells,
        "signature": {"kind": "fixture"},
    }


def _request():
    return ModelRequest("unused", "system", "user", {}, None, None, None, 5, 0, 100)


def _plan(*extra):
    return ResolvedProductPlan(
        "enterprise",
        "test",
        "enterprise",
        FREE_CAPABILITIES | frozenset(extra),
        "valid",
        2,
        False,
    )


class RoutingPolicyTests(unittest.TestCase):
    def test_timeout_falls_back_to_entitled_anthropic(self):
        policy = load_routing_policy(_document(), verify_signature=lambda _value: True)
        clients = {
            "openai": _Client(AIPlanningError("timeout", "timeout")),
            "anthropic": _Client(ModelResponse("{}", cost=0.1)),
            "moonshot": _Client(ModelResponse("{}", cost=0.1)),
        }
        result = PolicyRouter(
            policy,
            clients,
            credentials={"openai": "x", "anthropic": "y"},
        ).execute(
            _request(),
            data_class=DataClass.INTERNAL,
            purpose="planning",
            destination="external-us",
            context_digest="a" * 64,
            product_plan=_plan("ai.provider.anthropic"),
        )
        self.assertEqual(result.provider, "anthropic")
        self.assertEqual([item.status for item in result.attempts], ["failed", "accepted"])

    def test_authentication_never_crosses_provider(self):
        policy = load_routing_policy(_document(), verify_signature=lambda _value: True)
        clients = {
            "openai": _Client(AIPlanningError("authentication_failed", "denied")),
            "anthropic": _Client(ModelResponse("{}", cost=0.1)),
            "moonshot": _Client(ModelResponse("{}", cost=0.1)),
        }
        with self.assertRaises(AIPlanningError) as raised:
            PolicyRouter(policy, clients, credentials={"openai": "x", "anthropic": "y"}).execute(
                _request(),
                data_class=DataClass.INTERNAL,
                purpose="planning",
                destination="external-us",
                context_digest="a" * 64,
                product_plan=_plan("ai.provider.anthropic"),
            )
        self.assertEqual(raised.exception.category, "authentication_failed")
        self.assertEqual(clients["anthropic"].requests, [])

    def test_restricted_data_never_leaves_local_environment(self):
        policy = load_routing_policy(_document(moonshot_enabled=True), verify_signature=lambda _value: True)
        clients = {name: _Client(ModelResponse("{}", cost=0.1)) for name in ("openai", "anthropic", "moonshot")}
        with self.assertRaises(AIPlanningError):
            PolicyRouter(
                policy,
                clients,
                credentials={"openai": "x", "anthropic": "y", "moonshot": "z"},
            ).execute(
                _request(),
                data_class=DataClass.RESTRICTED,
                purpose="planning",
                destination="external-us",
                context_digest="a" * 64,
                product_plan=_plan("ai.provider.anthropic", "ai.provider.moonshot"),
            )
        self.assertTrue(all(not client.requests for client in clients.values()))

    def test_alias_and_unsigned_policy_are_rejected(self):
        document = _document()
        document["cells"][0]["model_snapshot"] = "gpt-5"
        with self.assertRaises(ValueError):
            load_routing_policy(document, verify_signature=lambda _value: True)
        with self.assertRaises(ValueError):
            load_routing_policy(_document(), verify_signature=lambda _value: False)


if __name__ == "__main__":
    unittest.main()
