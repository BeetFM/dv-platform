import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.scenarios import build_deterministic_scenarios
from dv_platform.core.config import default_config, validate_config
from dv_platform.core.models import (
    ClaimStatus,
    RTLControlDomain,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLPort,
    VerificationDepthPolicy,
    VerificationTarget,
)


def _policy(**overrides: str) -> VerificationDepthPolicy:
    parameters = {
        "profile": "bounded_sram",
        "clock": "clk",
        "reset": "rst_n",
        "read_during_write": "write_first",
        "initialization": "zero",
        "read_enable": "read_enable",
        "read_address": "read_address",
        "read_data": "read_data",
        "port0_request": "port0_request",
        "port0_write_enable": "port0_write_enable",
        "port0_address": "port0_address",
        "port0_write_data": "port0_write_data",
        "port0_byte_enable": "port0_byte_enable",
        "port0_grant": "port0_grant",
        "port1_request": "port1_request",
        "port1_write_enable": "port1_write_enable",
        "port1_address": "port1_address",
        "port1_write_data": "port1_write_data",
        "port1_byte_enable": "port1_byte_enable",
        "port1_grant": "port1_grant",
        "arbitration": "round_robin",
        "protection": "parity",
        "error_signal": "parity_error",
        "inject_error": "inject_error",
        "max_latency_cycles": "4",
        **overrides,
    }
    return VerificationDepthPolicy("memory", "memory_bounded_qualified", "storage", tuple(sorted(parameters.items())))


def _module() -> RTLModule:
    scalar_inputs = (
        "clk",
        "rst_n",
        "read_enable",
        "port0_request",
        "port0_write_enable",
        "port1_request",
        "port1_write_enable",
        "inject_error",
    )
    ports = [RTLPort(name, "input") for name in scalar_inputs]
    ports.extend(RTLPort(name, "input", width=3) for name in ("read_address", "port0_address", "port1_address"))
    ports.extend(RTLPort(name, "input", width=16) for name in ("port0_write_data", "port1_write_data"))
    ports.extend(RTLPort(name, "input", width=2) for name in ("port0_byte_enable", "port1_byte_enable"))
    ports.extend(
        (
            RTLPort("read_data", "output", width=16),
            RTLPort("port0_grant", "output"),
            RTLPort("port1_grant", "output"),
            RTLPort("parity_error", "output"),
        )
    )
    return RTLModule(
        "memory_bounded_qualified",
        port_details=tuple(ports),
        memories=(RTLMemory("storage", element_width=16, depth=8, address_width=3),),
        memory_accesses=(
            RTLMemoryAccess(
                "read",
                "storage",
                "read",
                address_signals=("read_address",),
                data_signals=("read_data",),
                domain_id="clk:posedge:rst_n:low",
                synchronous=True,
            ),
            RTLMemoryAccess(
                "write",
                "storage",
                "write",
                address_signals=("selected_address",),
                data_signals=("merged_word",),
                enable_signals=("accepted_write",),
                domain_id="clk:posedge:rst_n:low",
                synchronous=True,
            ),
        ),
        control_domains=(RTLControlDomain("clk:posedge:rst_n:low", "clk", reset="rst_n", reset_active_low=True),),
    )


class MemoryDepthTests(unittest.TestCase):
    def test_bounded_sram_policy_requires_complete_normalized_contract(self) -> None:
        claim = validate_depth_policies(_module(), (_policy(),))[0]

        self.assertEqual(claim.status, ClaimStatus.SUPPORTED)

    def test_bounded_sram_policy_fails_closed_on_width_and_access_gaps(self) -> None:
        wrong_width = replace(
            _module(),
            port_details=tuple(
                replace(port, width=1) if port.name == "port0_byte_enable" else port for port in _module().port_details
            ),
        )
        no_read = replace(
            _module(), memory_accesses=tuple(access for access in _module().memory_accesses if access.kind == "write")
        )

        self.assertEqual(validate_depth_policies(wrong_width, (_policy(),))[0].status, ClaimStatus.CONTRADICTED)
        self.assertEqual(validate_depth_policies(no_read, (_policy(),))[0].status, ClaimStatus.MISSING_EVIDENCE)

    def test_bounded_sram_configuration_rejects_unqualified_variants(self) -> None:
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                depth_policies=(_policy(profile="guess", arbitration="fixed_priority", protection="secded"),),
            )
            messages = {item.message for item in validate_config(config)}

        self.assertTrue(any("Invalid memory profile" in message for message in messages))
        self.assertTrue(any("Invalid memory arbitration" in message for message in messages))
        self.assertTrue(any("Invalid memory protection" in message for message in messages))

    def test_bounded_sram_scenario_fails_closed_when_normalized_dependencies_disappear(self) -> None:
        plan = create_initial_plan(_module(), (VerificationTarget.COCOTB,), depth_policies=(_policy(),))
        memory = plan.memories[0]

        missing_shape = replace(plan, memories=(replace(memory, depth=None),), scenarios=())
        missing_domain = replace(plan, control_domains=(), scenarios=())
        missing_check = replace(plan, check_details=(), scenarios=())

        self.assertFalse(build_deterministic_scenarios(missing_shape))
        self.assertFalse(build_deterministic_scenarios(missing_domain))
        self.assertFalse(build_deterministic_scenarios(missing_check))


if __name__ == "__main__":
    unittest.main()
