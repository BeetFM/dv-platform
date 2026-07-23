"""UVM register protocol rendering."""

from __future__ import annotations

from dv_platform.agent.protocols import RegisterModel
from dv_platform.core.models import (
    RTLProtocol,
    VerificationPlan,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.signals import (
    port_names,
    primary_clock_name,
    primary_reset,
)
from dv_platform.generators.uvm_common import _safe_identifier


def _uvm_register_build_lines(module_name: str, index: int, register: RegisterModel) -> tuple[str, ...]:
    name = _safe_identifier(register.name)
    if register.offset is None:
        raise ValueError(f"UVM RAL requires an exact offset for {register.name}")
    offset = register.offset
    return (
        f'            {name} = {module_name}_reg_{index}::type_id::create("{name}");',
        f'            {name}.configure(this, null, "");',
        f"            {name}.build();",
        f'            default_map.add_reg({name}, \'h{offset:x}, "RW");',
    )


def _protocol_package_content(
    plan: VerificationPlan,
    module_name: str,
    sink: RTLProtocol,
    source: RTLProtocol,
) -> str:
    presentation = _protocol_uvm_presentation(plan, module_name, sink, source)
    presentation["_plan"] = plan
    presentation["protocol_header"] = ""
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _protocol_uvm_presentation(
    plan: VerificationPlan,
    module_name: str,
    sink: RTLProtocol,
    source: RTLProtocol,
) -> dict[str, object]:
    width = sink.data_width or source.data_width or 1
    clock = sink.clock or source.clock or primary_clock_name(plan, port_names(plan)) or "clk"
    reset = primary_reset(plan, port_names(plan))
    reset_context = None
    if reset is not None:
        active_low = reset.active_low if reset.active_low is not None else reset.name.endswith("_n")
        active, inactive = ("1'b0", "1'b1") if active_low else ("1'b1", "1'b0")
        reset_context = {"name": reset.name, "active": active, "inactive": inactive}
    return {
        "artifact_kind": "protocol_package",
        "module": plan.module,
        "module_name": module_name,
        "width": width,
        "clock": clock,
        "sink": {"valid": sink.valid, "ready": sink.ready, "data": sink.data},
        "source": {"valid": source.valid, "ready": source.ready, "data": source.data},
        "reset": reset_context,
    }
