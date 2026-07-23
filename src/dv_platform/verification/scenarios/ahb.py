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


def _ahb_lite_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    """Build the fail-closed, single-beat AHB-Lite slave profile."""

    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = ("haddr", "htrans", "hwrite", "hready", "hreadyout", "hresp", "hsel", "hwdata", "hrdata")
    slave_outputs = {"hreadyout", "hresp", "hrdata"}
    direction_mismatches = tuple(
        name for name in required if directions.get(name) != ("output" if name in slave_outputs else "input")
    )
    reset = next((item for item in plan.resets if item.name == model.reset_domain), None)
    known_registers = tuple(
        register
        for register in plan.register_models
        if register.offset is not None
        and register.source != "unknown"
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
    ready = (
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
        "ahb_lite_single_beat",
        plan.targets,
        ready,
        "scenario lacks complete AHB-Lite signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    return [
        VerificationScenario(
            scenario_id=_scenario_id(plan.module, "ahb_lite_single_beat", "bus"),
            kind="ahb_lite_single_beat",
            stimulus=(
                ScenarioStimulus("ahb_lite_profile", parameters=profile),
                *register_stimuli,
                ScenarioStimulus("ahb_read", parameters=(("address", str(valid_address)),)),
                ScenarioStimulus("ahb_write", parameters=(("address", str(valid_address)),)),
                ScenarioStimulus("ahb_idle"),
            ),
            oracle=ScenarioOracle("single_beat_register_model", bindings.get("hrdata"), "mapped register state"),
            completion=ScenarioCompletion("signal", bindings.get("hreadyout"), "1", 16),
            coverage_goals=(
                ScenarioCoverageGoal(
                    f"{plan.module}:coverage:ahb-lite-single-beat",
                    "protocol_transfer",
                    (
                        "reset",
                        "idle",
                        "read-completion",
                        "write-completion",
                        "wait-state",
                        "stable-control",
                        "invalid-address",
                        "hresp-error",
                        "reset-recovery",
                    ),
                ),
            ),
            supported_targets=targets,
            target_states=target_states,
            requirement_ids=_requirement_ids(plan, ("protocol", "register", "reset")),
            check_ids=checks,
            evidence_refs=tuple(
                dict.fromkeys(
                    (*model.evidence_refs, *(ref for register in known_registers for ref in register.evidence_refs))
                )
            ),
            executable=ready and bool(targets),
        )
    ]
