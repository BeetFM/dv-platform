import ast
import unittest
from dataclasses import replace

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.scenarios import _cdc_scenarios
from dv_platform.core.models import (
    ClaimStatus,
    RTLCDCPath,
    RTLControlDomain,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLPort,
    VerificationDepthPolicy,
    VerificationTarget,
)
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.formal import FormalGenerator


def _policy(**replacements: str) -> VerificationDepthPolicy:
    parameters = {
        "structure": "async_fifo",
        "min_stages": "2",
        "max_latency_cycles": "32",
        "write_clock": "wclk",
        "write_reset": "wrst_n",
        "write_enable": "w_en",
        "write_data": "w_data",
        "write_binary_pointer": "w_ptr_bin",
        "write_gray_pointer": "w_ptr_gray",
        "write_gray_sync": "w_gray_sync",
        "full_signal": "full",
        "read_clock": "rclk",
        "read_reset": "rrst_n",
        "read_enable": "r_en",
        "read_data": "r_data",
        "read_binary_pointer": "r_ptr_bin",
        "read_gray_pointer": "r_ptr_gray",
        "read_gray_sync": "r_gray_sync",
        "empty_signal": "empty",
        **replacements,
    }
    return VerificationDepthPolicy("cdc", "async_fifo", "storage", tuple(sorted(parameters.items())))


def _module(*, depth: int = 4, stages: int = 2) -> RTLModule:
    widths = {
        "wclk": 1,
        "wrst_n": 1,
        "w_en": 1,
        "w_data": 8,
        "full": 1,
        "w_ptr_bin": 3,
        "w_ptr_gray": 3,
        "r_gray_meta": 3,
        "r_gray_sync": 3,
        "rclk": 1,
        "rrst_n": 1,
        "r_en": 1,
        "r_data": 8,
        "empty": 1,
        "r_ptr_bin": 3,
        "r_ptr_gray": 3,
        "w_gray_meta": 3,
        "w_gray_sync": 3,
    }
    inputs = {"wclk", "wrst_n", "w_en", "w_data", "rclk", "rrst_n", "r_en"}
    return RTLModule(
        "async_fifo",
        ports=tuple(widths),
        port_details=tuple(
            RTLPort(name, "input" if name in inputs else "output", width=width) for name, width in widths.items()
        ),
        memories=(RTLMemory("storage", element_width=8, depth=depth, address_width=2),),
        memory_accesses=(
            RTLMemoryAccess(
                "write", "storage", "write", ("write_address",), ("w_data",), ("w_en", "full"), "write", True
            ),
            RTLMemoryAccess("read", "storage", "read", ("read_address",), ("r_data",), ("r_en", "empty"), "read", True),
        ),
        control_domains=(
            RTLControlDomain("write", "wclk", reset="wrst_n", reset_active_low=True),
            RTLControlDomain("read", "rclk", reset="rrst_n", reset_active_low=True),
        ),
        cdc_paths=(
            RTLCDCPath(
                "wgray",
                "w_ptr_gray",
                "write",
                "read",
                "two_flop",
                stages,
                ("w_gray_meta", "w_gray_sync")[:stages],
                False,
                False,
            ),
            RTLCDCPath(
                "rgray",
                "r_ptr_gray",
                "read",
                "write",
                "two_flop",
                stages,
                ("r_gray_meta", "r_gray_sync")[:stages],
                False,
                False,
            ),
        ),
    )


class AsyncFIFOQualificationTests(unittest.TestCase):
    def test_scenario_construction_rejects_missing_domains_and_checks(self) -> None:
        plan = create_initial_plan(
            _module(),
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=(_policy(),),
        )
        self.assertEqual(_cdc_scenarios(replace(plan, control_domains=())), [])
        self.assertEqual(_cdc_scenarios(replace(plan, check_details=())), [])

    def test_policy_builds_renderer_backed_scenario_and_properties(self) -> None:
        module = _module()
        policy = _policy()
        self.assertEqual(validate_depth_policies(module, (policy,))[0].status, ClaimStatus.SUPPORTED)

        plan = create_initial_plan(
            module,
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=(policy,),
        )
        scenario = next(item for item in plan.scenarios if item.kind == "cdc_async_fifo")
        self.assertTrue(scenario.executable)
        self.assertEqual(set(scenario.supported_targets), {VerificationTarget.COCOTB, VerificationTarget.FORMAL})
        self.assertIn("wraparound", scenario.coverage_goals[0].bins)
        cocotb = CocotbGenerator().generate(plan)[0].content
        ast.parse(cocotb)
        self.assertIn("FIFO ordering mismatch", cocotb)
        self.assertIn("write Gray pointer changed by more than one bit", cocotb)
        formal = FormalGenerator("structural").generate(plan)[0].content
        self.assertIn("a_async_fifo_1_full_equation", formal)
        self.assertIn("a_async_fifo_1_empty_equation", formal)
        self.assertIn("c_async_fifo_1_write", formal)

    def test_ambiguous_or_contradictory_fifo_shapes_fail_closed(self) -> None:
        cases = (
            (_module(depth=3), _policy(), ClaimStatus.CONTRADICTED),
            (_module(stages=1), _policy(), ClaimStatus.CONTRADICTED),
            (_module(), _policy(read_clock="wclk"), ClaimStatus.CONTRADICTED),
            (_module(), _policy(read_data="missing"), ClaimStatus.MISSING_EVIDENCE),
        )
        for module, policy, expected in cases:
            with self.subTest(expected=expected, parameters=policy.parameters):
                self.assertEqual(validate_depth_policies(module, (policy,))[0].status, expected)
                plan = create_initial_plan(
                    module,
                    (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                    depth_policies=(policy,),
                )
                self.assertFalse(any(item.kind == "cdc_async_fifo" for item in plan.scenarios))


if __name__ == "__main__":
    unittest.main()
