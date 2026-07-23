# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Deterministic construction and validation of executable verification intent."""

from __future__ import annotations

import json

from dv_platform.agent.protocols import ProtocolModel
from dv_platform.core.models import (
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    VerificationPlan,
    VerificationScenario,
)


def _axi4_lite_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = (
        "awaddr",
        "awvalid",
        "awready",
        "wdata",
        "wstrb",
        "wvalid",
        "wready",
        "bresp",
        "bvalid",
        "bready",
        "araddr",
        "arvalid",
        "arready",
        "rdata",
        "rresp",
        "rvalid",
        "rready",
    )
    slave_outputs = {"awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid"}
    direction_mismatches = tuple(
        name for name in required if directions.get(name) != ("output" if name in slave_outputs else "input")
    )
    reset = next((item for item in plan.resets if item.name == model.reset_domain), None)
    known_registers = tuple(
        register
        for register in plan.register_models
        if register.offset is not None
        and register.source != "unknown"
        and register.byte_enable_behavior != "unknown"
        and register.invalid_address_behavior != "unknown"
        and register.fields
        and all(
            field.access.lower() in {"rw", "ro", "w1c"} and field.reset_value is not None for field in register.fields
        )
    )
    valid_address = min((register.offset for register in known_registers if register.offset is not None), default=0)
    invalid_address = max(
        (register.offset + max(1, register.width // 8) for register in known_registers if register.offset is not None),
        default=4,
    )
    profile = tuple(
        sorted(
            (
                *((f"binding.{name}", actual) for name, actual in bindings.items()),
                ("clock", model.clock_domain or ""),
                ("reset", model.reset_domain or ""),
                ("reset_active_low", str(reset.active_low).lower() if reset and reset.active_low is not None else ""),
                ("valid_address", str(valid_address)),
                ("invalid_address", str(invalid_address)),
            )
        )
    )
    register_stimuli = tuple(
        ScenarioStimulus(
            "register_spec",
            parameters=(
                (
                    "json",
                    json.dumps(
                        {
                            "byte_enable_behavior": register.byte_enable_behavior,
                            "fields": [
                                {
                                    "access": field.access.lower(),
                                    "lsb": field.lsb,
                                    "msb": field.msb,
                                    "name": field.name,
                                    "reset": field.reset_value,
                                }
                                for field in register.fields
                            ],
                            "invalid_address_behavior": register.invalid_address_behavior,
                            "name": register.name,
                            "offset": register.offset,
                            "width": register.width,
                        },
                        sort_keys=True,
                        separators=(",", ":"),
                    ),
                ),
            ),
        )
        for register in known_registers
    )
    checks = tuple(
        dict.fromkeys((*_check_ids(plan, "protocol"), *_check_ids(plan, "reset"), *_check_ids(plan, "register_access")))
    )
    axi_ready = (
        all(name in bindings for name in required)
        and not direction_mismatches
        and not model.unsupported_semantics
        and model.clock_domain is not None
        and reset is not None
        and reset.active_low is not None
        and bool(known_registers)
        and bool(checks)
    )
    target_states = _qualified_target_states(
        "axi4_lite_single_outstanding",
        plan.targets,
        axi_ready,
        "scenario lacks complete AXI4-Lite signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    return [
        VerificationScenario(
            scenario_id=_scenario_id(plan.module, "axi4_lite_single_outstanding", "bus"),
            kind="axi4_lite_single_outstanding",
            stimulus=(
                ScenarioStimulus("axi4_lite_profile", parameters=profile),
                *register_stimuli,
                ScenarioStimulus("axi_write", parameters=(("outstanding", "1"), ("orders", "AW-W,W-AW,same"))),
                ScenarioStimulus("axi_read", parameters=(("outstanding", "1"),)),
                ScenarioStimulus("backpressure", parameters=(("channels", "B,R"),)),
            ),
            oracle=ScenarioOracle("in_order_response", expected="one response per accepted request"),
            completion=ScenarioCompletion("bounded_responses", timeout_cycles=4),
            coverage_goals=(
                ScenarioCoverageGoal(
                    f"{plan.module}:coverage:axi4-lite-ordering",
                    "cross",
                    (
                        "reset",
                        "AW-before-W",
                        "W-before-AW",
                        "same-cycle",
                        "B-backpressure",
                        "R-backpressure",
                        "WSTRB",
                        "invalid-address",
                        "BRESP-error",
                        "RRESP-error",
                    ),
                ),
            ),
            supported_targets=targets,
            target_states=target_states,
            requirement_ids=_requirement_ids(plan, ("protocol", "register")),
            check_ids=checks,
            evidence_refs=model.evidence_refs,
            executable=axi_ready and bool(targets),
        )
    ]
