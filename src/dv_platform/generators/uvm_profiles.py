"""UVM profile and agent rendering."""

from __future__ import annotations

from dv_platform.agent.protocols import ProtocolModel, RegisterField
from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import (
    VerificationPlan,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.uvm_common import _paired_protocol, _safe_identifier
from dv_platform.generators.uvm_protocol import _protocol_package_content


def _package_content(plan: VerificationPlan) -> str:
    module_name = _safe_identifier(plan.module)
    pair = _paired_protocol(plan)
    if pair is not None:
        return _protocol_package_content(plan, module_name, *pair)
    if any(model.profile_id and model.profile_id.endswith("-1.0") for model in plan.protocol_models):
        return _profile_uvm_package_content(plan, module_name)
    presentation: dict[str, object] = {
        "_plan": plan,
        "protocol_header": "",
        "artifact_kind": "scaffold_package",
        "module": plan.module,
        "module_name": module_name,
    }
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _profile_uvm_package_content(plan: VerificationPlan, module_name: str) -> str:
    """Emit reusable multi-agent UVM contracts for shared protocol profiles."""

    presentation = _profile_uvm_presentation(plan, module_name)
    presentation["_plan"] = plan
    presentation["protocol_header"] = ""
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _profile_uvm_presentation(plan: VerificationPlan, module_name: str) -> dict[str, object]:
    """Build semantic context for the package-owned multi-agent template."""

    models = tuple(model for model in plan.protocol_models if model.profile_id and model.profile_id.endswith("-1.0"))
    model_contexts = []
    for index, model in enumerate(models):
        stem = f"{module_name}_p{index}"
        transaction_fields = _uvm_transaction_fields(plan, model)
        model_contexts.append(
            {
                "index": index,
                "stem": stem,
                "profile_id": model.profile_id,
                "instance_id": model.instance_id,
                "role": model.role,
                "fields": tuple({"name": name, "width": width} for name, width in transaction_fields),
                "maximum_burst_length": max(1, model.maximum_burst_length),
                "maximum_outstanding": max(1, model.maximum_outstanding),
                "repeat_count": min(model.maximum_outstanding * 2, 32),
                "agent": _profile_uvm_agent_presentation(
                    plan,
                    module_name,
                    stem,
                    model,
                    transaction_fields,
                ),
            }
        )
    return {
        "artifact_kind": "profile_package",
        "module": plan.module,
        "module_name": module_name,
        "models": model_contexts,
        "ral": _uvm_ral_presentation(plan, module_name),
        "timeout_ns": max((model.timeout_cycles for model in models), default=32) * 1000,
    }


def _uvm_transaction_fields(plan: VerificationPlan, model: ProtocolModel) -> tuple[tuple[str, int], ...]:
    ports = {port.name: port for port in plan.ports}
    bindings = dict(model.signal_bindings)
    fields: list[tuple[str, int]] = []
    for channel in model.channels:
        for canonical in channel.payload_fields:
            physical = bindings.get(canonical)
            if physical is None or any(name == canonical for name, _width in fields):
                continue
            port = ports.get(physical)
            fields.append((_safe_identifier(canonical), max(1, port.width if port and port.width else 1)))
    return tuple(fields)


def _profile_uvm_handshake(model: ProtocolModel) -> tuple[str, str, int] | None:
    bindings = dict(model.signal_bindings)
    for valid, ready, accepted in (
        ("awvalid", "awready", 1),
        ("wvalid", "wready", 1),
        ("bvalid", "bready", 1),
        ("arvalid", "arready", 1),
        ("rvalid", "rready", 1),
        ("tvalid", "tready", 1),
        ("valid", "ready", 1),
        ("a_valid", "a_ready", 1),
        ("d_valid", "d_ready", 1),
        ("stb", "stall", 0),
        ("read", "waitrequest", 0),
        ("write", "waitrequest", 0),
        ("hsel", "hready", 1),
    ):
        if valid in bindings and ready in bindings:
            return valid, ready, accepted
    if "stb" in bindings and "ack" in bindings:
        return "stb", "ack", 1
    return None


def _profile_uvm_agent_lines(
    plan: VerificationPlan,
    module_name: str,
    stem: str,
    model: ProtocolModel,
    transaction_fields: tuple[tuple[str, int], ...],
) -> list[str]:
    presentation = _profile_uvm_agent_presentation(
        plan,
        module_name,
        stem,
        model,
        transaction_fields,
    )
    presentation["_plan"] = plan
    presentation["protocol_header"] = ""
    return render_target("uvm", presentation).splitlines()  # type: ignore[arg-type]


def _profile_uvm_agent_presentation(
    plan: VerificationPlan,
    module_name: str,
    stem: str,
    model: ProtocolModel,
    transaction_fields: tuple[tuple[str, int], ...],
) -> dict[str, object]:
    handshake = _profile_uvm_handshake(model)
    if handshake is None:
        raise ValueError(f"UVM profile {model.profile_id} has no recognized acceptance handshake")
    valid_name, ready_name, accepted = handshake
    bindings = dict(model.signal_bindings)
    directions = dict(model.signal_directions)
    valid, ready = bindings[valid_name], bindings[ready_name]
    clock = model.clock_domain or "clk"
    active = directions.get(valid_name) == "input"
    accepted_expression = f"vif.{ready}" if accepted else f"!vif.{ready}"
    monitor_acceptance = f"vif.{valid} && ({accepted_expression})"
    input_payloads = tuple(
        (canonical, bindings[canonical])
        for canonical, _width in transaction_fields
        if canonical in bindings and directions.get(canonical) == "input"
    )
    id_field = next(
        (name for name, _width in transaction_fields if name.endswith("id") or name.endswith("source")), None
    )
    last_field = next(
        (name for name, _width in transaction_fields if name.endswith("last") or name == "endofpacket"), None
    )
    id_expression = f"observed.{id_field}" if id_field else "observed_count"
    last_expression = f"observed.{last_field}" if last_field else "1'b1"
    coverage_comments = ", ".join(model.coverage_bins) or "acceptance"
    profile_coverpoints, profile_crosses = _profile_covergroup_lines(transaction_fields)
    compare_expression = (
        " && ".join(f"expected.{canonical} == actual.{canonical}" for canonical, _physical in input_payloads) or "1'b1"
    )
    return {
        "artifact_kind": "profile_agent",
        "module_name": module_name,
        "stem": stem,
        "active": active,
        "accepted": accepted,
        "valid": valid,
        "ready": ready,
        "clock": clock,
        "input_payloads": tuple(
            {"canonical": canonical, "physical": physical} for canonical, physical in input_payloads
        ),
        "transaction_fields": tuple(
            {"canonical": canonical, "physical": bindings[canonical]} for canonical, _width in transaction_fields
        ),
        "monitor_acceptance": monitor_acceptance,
        "accepted_expression": accepted_expression,
        "id_expression": id_expression,
        "last_expression": last_expression,
        "coverage_comments": coverage_comments,
        "maximum_beat": max(1, model.maximum_burst_length - 1),
        "profile_coverpoints": profile_coverpoints,
        "profile_crosses": profile_crosses,
        "compare_expression": compare_expression,
        "canonical_fields": ", ".join(name for name, _width in transaction_fields) or "none",
    }


def _profile_covergroup_lines(
    transaction_fields: tuple[tuple[str, int], ...],
) -> tuple[tuple[str, ...], tuple[str, ...]]:
    """Render protocol-field coverpoints and stable category crosses."""

    categories: dict[str, list[str]] = {
        "burst": [],
        "response": [],
        "mask": [],
        "route": [],
        "packet": [],
    }
    coverpoints: list[str] = []
    for field, _width in transaction_fields:
        normalized = field.lower()
        category = next(
            (
                name
                for name, terms in (
                    ("burst", ("len", "size", "burst", "burstcount", "cti", "bte")),
                    ("response", ("resp", "response", "denied", "corrupt", "error", "err", "rty")),
                    ("mask", ("strb", "keep", "sel", "byteenable", "mask", "empty")),
                    ("route", ("id", "source", "dest", "channel")),
                    ("packet", ("last", "startofpacket", "endofpacket")),
                )
                if any(term in normalized for term in terms)
            ),
            None,
        )
        if category is None:
            continue
        label = f"cp_{_safe_identifier(field)}"
        coverpoints.append(f"            {label}: coverpoint tr.{field};")
        categories[category].append(label)
    crosses: list[str] = []
    for left, right in (("burst", "response"), ("mask", "packet"), ("route", "packet")):
        if categories[left] and categories[right]:
            crosses.append(f"            {left}_x_{right}: cross {categories[left][0]}, {categories[right][0]};")
    return tuple(coverpoints), tuple(crosses)


def _uvm_ral_lines(plan: VerificationPlan, module_name: str) -> list[str]:
    presentation = _uvm_ral_presentation(plan, module_name)
    presentation["_plan"] = plan
    presentation["protocol_header"] = ""
    return render_target("uvm", presentation).splitlines()  # type: ignore[arg-type]


def _uvm_ral_presentation(plan: VerificationPlan, module_name: str) -> dict[str, object]:
    for register in plan.register_models:
        if register.offset is None:
            raise ValueError(f"UVM RAL requires an exact offset for {register.name}")
    return {
        "artifact_kind": "ral_fragment",
        "module_name": module_name,
        "registers": tuple(
            {
                "index": index,
                "type": f"{module_name}_reg_{index}",
                "name": register.name,
                "identifier": _safe_identifier(register.name),
                "width": register.width,
                "offset_hex": f"{register.offset:x}" if register.offset is not None else None,
                "fields": tuple(_uvm_field_context(field) for field in register.fields),
            }
            for index, register in enumerate(plan.register_models)
        ),
    }


def _uvm_field_configuration(field: RegisterField) -> str:
    context = _uvm_field_context(field)
    return (
        f'            {context["name"]} = uvm_reg_field::type_id::create("{context["name"]}"); '
        f'{context["name"]}.configure(this, {context["width"]}, {context["lsb"]}, "{context["access"]}", '
        f"0, 'h{context['reset_hex']}, {context['has_reset']}, {context['is_rand']}, 0);"
    )


def _uvm_field_context(field: RegisterField) -> dict[str, object]:
    name = _safe_identifier(field.name)
    width = field.msb - field.lsb + 1
    lsb = field.lsb
    access = field.access.upper().replace("_", "")
    supported = {
        "RO",
        "RW",
        "RC",
        "RS",
        "WRC",
        "WRS",
        "WC",
        "WS",
        "WSRC",
        "WCRS",
        "W1C",
        "W1S",
        "W1T",
        "W0C",
        "W0S",
        "W0T",
        "WO",
        "WOC",
        "WOS",
        "W1",
        "WO1",
    }
    if access not in supported:
        access = "RO" if field.reserved else "RW"
    reset_text = field.reset_value
    reset = sv_numeric_literal_to_int(str(reset_text), width=width) if reset_text is not None else None
    if reset is None and reset_text is not None:
        try:
            reset = int(str(reset_text), 0)
        except ValueError:
            reset = 0
    has_reset = int(reset_text is not None)
    is_rand = int(access in {"RW", "WRC", "WRS"} and not field.reserved)
    return {
        "name": name,
        "width": width,
        "lsb": lsb,
        "access": access,
        "reset_hex": f"{reset or 0:x}",
        "has_reset": has_reset,
        "is_rand": is_rand,
    }
