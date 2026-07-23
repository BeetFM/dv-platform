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


def _apb4_scenarios(plan: VerificationPlan, model: ProtocolModel) -> list[VerificationScenario]:
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    required = ("psel", "penable", "pwrite", "paddr", "pwdata", "prdata", "pready", "pstrb", "pslverr")
    missing = tuple(name for name in required if name not in bindings)
    direction_mismatches = tuple(
        name
        for name in required
        if directions.get(name) != ("output" if name in {"prdata", "pready", "pslverr"} else "input")
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
    profile_parameters = tuple(
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
    check_ids = tuple(dict.fromkeys((*_check_ids(plan, "protocol"), *_check_ids(plan, "reset"))))
    requirement_ids = _requirement_ids(plan, ("protocol", "register", "reset"))
    apb_ready = (
        not missing
        and not direction_mismatches
        and not model.unsupported_semantics
        and model.clock_domain is not None
        and reset is not None
        and reset.active_low is not None
        and bool(known_registers)
        and bool(check_ids)
    )
    target_states = _qualified_target_states(
        "apb4_transfer",
        plan.targets,
        apb_ready,
        "scenario lacks complete APB signal, reset, check, or register scoreboard evidence",
    )
    targets = _executable_targets(target_states)
    scenario = VerificationScenario(
        scenario_id=_scenario_id(plan.module, "apb4_transfer", "bus"),
        kind="apb4_transfer",
        stimulus=(
            ScenarioStimulus("apb4_profile", parameters=profile_parameters),
            ScenarioStimulus("reset", model.reset_domain, parameters=(("cycles", "2"),)),
            ScenarioStimulus("drive", bindings.get("psel"), "1"),
            ScenarioStimulus("drive", bindings.get("penable"), "0"),
            ScenarioStimulus("drive", bindings.get("pwrite"), "0"),
            ScenarioStimulus("next_cycle"),
            ScenarioStimulus("drive", bindings.get("penable"), "1"),
        ),
        oracle=ScenarioOracle("handshake", bindings.get("pready"), "1", "access_phase"),
        completion=ScenarioCompletion("signal", bindings.get("pready"), "1", 32),
        coverage_goals=(
            ScenarioCoverageGoal(
                f"{plan.module}:coverage:apb4-transfer",
                "protocol_transfer",
                (
                    "reset",
                    "setup",
                    "access",
                    "wait-state",
                    "read-completion",
                    "write-completion",
                    "invalid-address",
                    "pslverr",
                ),
            ),
        ),
        supported_targets=targets,
        target_states=target_states,
        requirement_ids=requirement_ids,
        check_ids=check_ids,
        evidence_refs=model.evidence_refs,
        executable=apb_ready and bool(targets),
    )
    scenarios = [scenario]
    for register in plan.register_models:
        known_behavior = register in known_registers
        register_checks = tuple(dict.fromkeys((*check_ids, *_register_check_ids(plan, register.name))))
        register_ready = apb_ready and known_behavior and bool(register_checks)
        register_target_states = _qualified_target_states(
            "apb4_register_access",
            plan.targets,
            register_ready,
            f"register {register.name} lacks complete APB scoreboard evidence or linked checks",
        )
        register_targets = _executable_targets(register_target_states)
        register_spec = json.dumps(
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
        )
        scenarios.append(
            VerificationScenario(
                scenario_id=_scenario_id(plan.module, "apb4_register_access", register.name),
                kind="apb4_register_access",
                stimulus=(
                    ScenarioStimulus("apb4_profile", parameters=profile_parameters),
                    ScenarioStimulus("register_spec", parameters=(("json", register_spec),)),
                    ScenarioStimulus("reset", model.reset_domain, parameters=(("cycles", "2"),)),
                    ScenarioStimulus(
                        "apb_write",
                        parameters=(("register", register.name), ("offset", str(register.offset or 0))),
                    ),
                    ScenarioStimulus(
                        "apb_read",
                        parameters=(("register", register.name), ("offset", str(register.offset or 0))),
                    ),
                ),
                oracle=ScenarioOracle("register_model", bindings.get("prdata"), register.name),
                completion=ScenarioCompletion("signal", bindings.get("pready"), "1", 32),
                coverage_goals=(
                    ScenarioCoverageGoal(
                        f"{plan.module}:coverage:register:{register.name}",
                        "register_access",
                        tuple(
                            dict.fromkeys(
                                (
                                    "reset-value",
                                    "read-completion",
                                    "write-completion",
                                    "pstrb",
                                    *(field.access.lower() for field in register.fields),
                                )
                            )
                        ),
                    ),
                ),
                supported_targets=register_targets,
                target_states=register_target_states,
                requirement_ids=requirement_ids,
                check_ids=register_checks,
                evidence_refs=tuple(dict.fromkeys((*model.evidence_refs, *register.evidence_refs))),
                executable=bool(register_ready and register_targets),
            )
        )
    return scenarios
