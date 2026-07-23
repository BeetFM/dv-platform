import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.core.config import default_config, validate_config
from dv_platform.core.models import (
    ClaimStatus,
    RTLControlDomain,
    RTLModule,
    RTLPort,
    VerificationDepthPolicy,
)


def formal_policy(**overrides: str) -> VerificationDepthPolicy:
    parameters = {
        "profile": "bounded_response",
        "clock": "clk",
        "reset": "rst_n",
        "trigger_signal": "trigger",
        "response_signal": "response",
        "invariant_signal": "invariant_ok",
        "max_latency_cycles": "2",
        "assume_trigger_pulse": "true",
        "require_response_causality": "true",
        **overrides,
    }
    return VerificationDepthPolicy(
        "formal", "formal_contract_qualified", "request_response", tuple(sorted(parameters.items()))
    )


def formal_module() -> RTLModule:
    return RTLModule(
        "formal_contract_qualified",
        port_details=(
            RTLPort("clk", "input"),
            RTLPort("rst_n", "input"),
            RTLPort("trigger", "input"),
            RTLPort("response", "output"),
            RTLPort("invariant_ok", "output"),
        ),
        control_domains=(
            RTLControlDomain("main", "clk", reset="rst_n", reset_active_low=True, asynchronous_reset=True),
        ),
    )


class FormalDepthTests(unittest.TestCase):
    def test_bounded_response_policy_requires_typed_observable_contract(self) -> None:
        claim = validate_depth_policies(formal_module(), (formal_policy(),))[0]

        self.assertEqual(claim.status, ClaimStatus.SUPPORTED)

    def test_bounded_response_policy_rejects_aliases_and_missing_assumptions(self) -> None:
        aliased = formal_policy(response_signal="trigger")
        missing_assumption = formal_policy(assume_trigger_pulse="false")

        self.assertEqual(validate_depth_policies(formal_module(), (aliased,))[0].status, ClaimStatus.CONTRADICTED)
        self.assertEqual(
            validate_depth_policies(formal_module(), (missing_assumption,))[0].status,
            ClaimStatus.MISSING_EVIDENCE,
        )

    def test_formal_configuration_rejects_unbounded_or_unknown_intent(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                depth_policies=(formal_policy(profile="free_form", max_latency_cycles="0"),),
            )
            messages = {item.message for item in validate_config(config)}

        self.assertTrue(any("Invalid formal profile" in message for message in messages))
        self.assertTrue(any("max_latency_cycles" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
