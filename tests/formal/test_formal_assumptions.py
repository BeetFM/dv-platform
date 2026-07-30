import unittest

from dv_platform.core.models import (
    ClaimStatus,
    RTLControlDomain,
    RTLModule,
    RTLPort,
    VerificationCheck,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.formal.generation import _formal_assumption_assertions
from dv_platform.verification.depth import validate_depth_policies
from dv_platform.verification.scenarios import build_deterministic_scenarios


def _module() -> RTLModule:
    return RTLModule(
        "top",
        port_details=(
            RTLPort("clk", "input", width=1),
            RTLPort("rst_n", "input", width=1),
            RTLPort("data_i", "input", width=8),
        ),
        control_domains=(RTLControlDomain("main", "clk", reset="rst_n", reset_active_low=True),),
    )


def _policy(**overrides: str) -> VerificationDepthPolicy:
    parameters = {
        "assumption": "range",
        "signal": "data_i",
        "clock": "clk",
        "reset": "rst_n",
        "reset_active": "low",
        "bound_cycles": "8",
        "minimum": "0",
        "maximum": "15",
        "engine": "sby",
        **overrides,
    }
    return VerificationDepthPolicy("formal_assumption", "top", "input_range", tuple(parameters.items()))


class FormalAssumptionTests(unittest.TestCase):
    def test_range_policy_builds_executable_sby_scenario_and_properties(self) -> None:
        policy = _policy()
        claims = validate_depth_policies(_module(), (policy,))
        plan = VerificationPlan(
            "top",
            (VerificationTarget.FORMAL,),
            ports=_module().port_details,
            control_domains=_module().control_domains,
            depth_policies=(policy,),
            claims=claims,
            check_details=(
                VerificationCheck(
                    "top:check:formal-range",
                    "Verify configured formal assumption input_range applies typed range semantics.",
                    "formal",
                    True,
                ),
            ),
        )
        scenarios = build_deterministic_scenarios(plan)
        planned = VerificationPlan(**{**plan.__dict__, "scenarios": scenarios})
        lines = _formal_assumption_assertions(planned, "rst_n", "1'b0", "1'b1", "clk")

        self.assertEqual(claims[0].status, ClaimStatus.SUPPORTED)
        self.assertEqual(len([item for item in scenarios if item.kind == "formal_assumption"]), 1)
        self.assertTrue(any("assume((data_i >= 0) && (data_i <= 15))" in line for line in lines))
        self.assertTrue(any("_witness" in line for line in lines))
        self.assertTrue(any("_completion" in line for line in lines))

    def test_unsupported_engine_and_invalid_bounds_fail_closed(self) -> None:
        cases = (
            (_policy(engine="jasper"), ClaimStatus.MISSING_EVIDENCE),
            (_policy(bound_cycles="0"), ClaimStatus.CONTRADICTED),
            (_policy(minimum="16", maximum="15"), ClaimStatus.CONTRADICTED),
            (_policy(assumption="inferred"), ClaimStatus.MISSING_EVIDENCE),
        )
        for policy, expected in cases:
            with self.subTest(parameters=dict(policy.parameters)):
                claim = validate_depth_policies(_module(), (policy,))[0]
                self.assertEqual(claim.status, expected)


if __name__ == "__main__":
    unittest.main()
