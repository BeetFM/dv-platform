import math
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.core.config import default_config, validate_config
from dv_platform.core.models import (
    ClaimStatus,
    RTLClock,
    RTLControlDomain,
    RTLModule,
    RTLPort,
    RTLReset,
    VerificationDepthPolicy,
    VerificationTarget,
)
from dv_platform.core.peripherals import PERIPHERAL_CONTRACTS
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.formal import FormalGenerator

INTEGER_VALUES = {
    "data_bits": 8,
    "clocks_per_bit": 4,
    "max_frame_cycles": 128,
    "word_bits": 8,
    "clock_divider": 2,
    "max_transfer_cycles": 256,
    "max_stretch_cycles": 8,
    "width": 4,
    "counter_width": 8,
    "irq_sources": 4,
    "max_event_cycles": 128,
}


def _width(value: int | str) -> int:
    if isinstance(value, int):
        return value
    if value == "irq_index_width":
        return max(1, math.ceil(math.log2(INTEGER_VALUES["irq_sources"])))
    return INTEGER_VALUES[value]


def _policy(kind: str, **changes: str) -> VerificationDepthPolicy:
    contract = PERIPHERAL_CONTRACTS[kind]
    parameters = {
        "profile": contract.profile,
        **{signal.name: signal.name for signal in contract.signals},
        **{name: str(INTEGER_VALUES[name]) for name, _minimum, _maximum in contract.integer_parameters},
        **{name: values[0] for name, values in contract.enum_parameters},
        **changes,
    }
    return VerificationDepthPolicy(kind, f"{kind}_qualified", "controller", tuple(sorted(parameters.items())))


def _module(kind: str) -> RTLModule:
    contract = PERIPHERAL_CONTRACTS[kind]
    ports = tuple(RTLPort(signal.name, signal.direction, width=_width(signal.width)) for signal in contract.signals)
    return RTLModule(
        f"{kind}_qualified",
        ports=tuple(port.name for port in ports),
        clocks=("clock",),
        resets=("reset",),
        port_details=ports,
        clock_details=(RTLClock("clock", "input"),),
        reset_details=(RTLReset("reset", "input", active_low=True),),
        control_domains=(RTLControlDomain("clock:posedge:reset:low", "clock", reset="reset", reset_active_low=True),),
    )


class PeripheralDepthTests(unittest.TestCase):
    def test_every_bounded_profile_validates_and_builds_both_target_scenario(self) -> None:
        for kind in PERIPHERAL_CONTRACTS:
            with self.subTest(kind=kind):
                policy = _policy(kind)
                claim = validate_depth_policies(_module(kind), (policy,))[0]
                self.assertEqual(claim.status, ClaimStatus.SUPPORTED, claim.statement)
                plan = create_initial_plan(
                    _module(kind),
                    (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                    depth_policies=(policy,),
                )
                scenario = next(item for item in plan.scenarios if item.kind == f"{kind}_bounded")
                self.assertTrue(scenario.executable)
                self.assertEqual(
                    scenario.supported_targets,
                    (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                )
                self.assertTrue(scenario.check_ids)
                cocotb_source = CocotbGenerator().generate(plan)[0].content
                compile(cocotb_source, f"generated_{kind}.py", "exec")
                self.assertIn(f"test_{kind}_qualified_scenario_", cocotb_source)
                formal_source = FormalGenerator().generate(plan)[0].content
                self.assertIn(f"a_{'gpio' if kind == 'gpio_timer_interrupt' else kind}_", formal_source)

    def test_profiles_fail_closed_on_missing_mapping_direction_width_and_domain(self) -> None:
        for kind, contract in PERIPHERAL_CONTRACTS.items():
            policy = _policy(kind)
            first_data = next(signal for signal in contract.signals if signal.name not in {"clock", "reset"})
            missing = replace(
                policy, parameters=tuple(item for item in policy.parameters if item[0] != first_data.name)
            )
            wrong_direction = replace(
                _module(kind),
                port_details=tuple(
                    replace(port, direction="output" if port.direction == "input" else "input")
                    if port.name == first_data.name
                    else port
                    for port in _module(kind).port_details
                ),
            )
            wrong_width = replace(
                _module(kind),
                port_details=tuple(
                    replace(port, width=(port.width or 1) + 1) if port.name == first_data.name else port
                    for port in _module(kind).port_details
                ),
            )
            no_domain = replace(_module(kind), control_domains=())
            with self.subTest(kind=kind):
                self.assertEqual(
                    validate_depth_policies(_module(kind), (missing,))[0].status,
                    ClaimStatus.MISSING_EVIDENCE,
                )
                self.assertEqual(
                    validate_depth_policies(wrong_direction, (policy,))[0].status,
                    ClaimStatus.CONTRADICTED,
                )
                self.assertEqual(
                    validate_depth_policies(wrong_width, (policy,))[0].status,
                    ClaimStatus.CONTRADICTED,
                )
                self.assertEqual(
                    validate_depth_policies(no_domain, (policy,))[0].status,
                    ClaimStatus.MISSING_EVIDENCE,
                )

    def test_configuration_rejects_unknown_and_out_of_range_peripheral_variants(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                depth_policies=(
                    _policy("uart", profile="guessed", clocks_per_bit="1"),
                    _policy("gpio_timer_interrupt", priority="round_robin"),
                ),
            )
            messages = {diagnostic.message for diagnostic in validate_config(config)}
        self.assertTrue(any("Invalid uart profile" in message for message in messages))
        self.assertTrue(any("clocks_per_bit must be between" in message for message in messages))
        self.assertTrue(any("Invalid gpio_timer_interrupt priority" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
