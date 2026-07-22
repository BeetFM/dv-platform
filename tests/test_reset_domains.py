import unittest

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.core.models import (
    ClaimStatus,
    RTLCDCPath,
    RTLControlDomain,
    RTLModule,
    RTLPort,
    RTLReset,
    VerificationDepthPolicy,
    VerificationTarget,
)


def _module(*, stages: int = 2) -> RTLModule:
    ports = (
        RTLPort("src_clk", "input"),
        RTLPort("src_rst_n", "input"),
        RTLPort("src_ready", "output"),
        RTLPort("dst_clk", "input"),
        RTLPort("dst_rst_n", "input"),
        RTLPort("dependency_meta", "output"),
        RTLPort("dependency_sync", "output"),
        RTLPort("dst_ready", "output"),
    )
    return RTLModule(
        "reset_domains",
        ports=tuple(port.name for port in ports),
        port_details=ports,
        reset_details=(
            RTLReset("src_rst_n", "input", active_low=True),
            RTLReset("dst_rst_n", "input", active_low=True),
        ),
        control_domains=(
            RTLControlDomain("source", "src_clk", reset="src_rst_n", reset_active_low=True, asynchronous_reset=True),
            RTLControlDomain(
                "destination", "dst_clk", reset="dst_rst_n", reset_active_low=True, asynchronous_reset=True
            ),
        ),
        cdc_paths=(
            RTLCDCPath(
                "reset-rdc",
                "src_ready",
                "source",
                "destination",
                "two_flop",
                stages,
                ("dependency_meta", "dependency_sync")[:stages],
                False,
                False,
            ),
        ),
    )


def _source_policy(**changes: str) -> VerificationDepthPolicy:
    parameters = {
        "clock": "src_clk",
        "release_cycles": "2",
        "asynchronous_assertion": "true",
        "ready_signal": "src_ready",
        "recovery_cycles": "1",
        "removal_cycles": "1",
        **changes,
    }
    return VerificationDepthPolicy("reset", "reset_domains", "src_rst_n", tuple(sorted(parameters.items())))


def _destination_policy(**changes: str) -> VerificationDepthPolicy:
    parameters = {
        "clock": "dst_clk",
        "release_cycles": "2",
        "asynchronous_assertion": "true",
        "ready_signal": "dst_ready",
        "depends_on_reset": "src_rst_n",
        "depends_on_ready": "src_ready",
        "dependency_sync_signal": "dependency_sync",
        "recovery_cycles": "1",
        "removal_cycles": "1",
        **changes,
    }
    return VerificationDepthPolicy("reset", "reset_domains", "dst_rst_n", tuple(sorted(parameters.items())))


class ResetDomainQualificationTests(unittest.TestCase):
    def test_qualified_policies_build_executable_reset_domain_scenarios(self) -> None:
        module = _module()
        policies = (_source_policy(), _destination_policy())
        claims = validate_depth_policies(module, policies)
        self.assertEqual({claim.status for claim in claims}, {ClaimStatus.SUPPORTED})

        plan = create_initial_plan(
            module,
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=policies,
        )
        scenarios = [item for item in plan.scenarios if item.kind == "reset_domain_sequence"]
        self.assertEqual(len(scenarios), 2)
        self.assertTrue(all(item.executable for item in scenarios))
        self.assertTrue(next(path for path in plan.cdc_paths if path.signal == "src_ready").safe)

    def test_incomplete_or_contradictory_reset_policies_fail_closed(self) -> None:
        cases = (
            (_module(), _source_policy(ready_signal="missing"), ClaimStatus.MISSING_EVIDENCE),
            (_module(), _source_policy(clock="wrong"), ClaimStatus.CONTRADICTED),
            (_module(stages=1), _destination_policy(), ClaimStatus.CONTRADICTED),
            (_module(), _destination_policy(depends_on_ready="missing"), ClaimStatus.MISSING_EVIDENCE),
            (_module(), _destination_policy(depends_on_reset="dst_rst_n"), ClaimStatus.CONTRADICTED),
        )
        for module, policy, expected in cases:
            with self.subTest(parameters=policy.parameters):
                self.assertEqual(validate_depth_policies(module, (policy,))[0].status, expected)
                plan = create_initial_plan(
                    module,
                    (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                    depth_policies=(policy,),
                )
                self.assertFalse(any(item.kind == "reset_domain_sequence" for item in plan.scenarios))

    def test_reset_dependency_cycles_are_rejected(self) -> None:
        source = _source_policy(
            depends_on_reset="dst_rst_n",
            depends_on_ready="dst_ready",
            dependency_sync_signal="dependency_sync",
        )
        destination = _destination_policy()
        claims = validate_depth_policies(_module(), (source, destination))
        self.assertTrue(all(claim.status == ClaimStatus.CONTRADICTED for claim in claims))
        self.assertTrue(all("cycle" in claim.statement for claim in claims))


if __name__ == "__main__":
    unittest.main()
