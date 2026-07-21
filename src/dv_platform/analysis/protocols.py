"""Deterministic recognition for the first control-plane protocol milestone."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from dv_platform.agent.protocols import ProtocolModel, ahb_lite_model, apb4_model, axi4_lite_model
from dv_platform.core.models import EvidenceKind, EvidenceRef, RTLModule, RTLPort


def recognize_axi4_lite(module: RTLModule) -> ProtocolModel | None:
    names = {port.name.lower() for port in module.port_details}
    required = {"awvalid", "awready", "wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready"}
    if not required.issubset(names):
        return None
    canonical = required | {"aclk", "aresetn", "awaddr", "wdata", "wstrb", "bresp", "araddr", "rdata", "rresp"}
    mapping = tuple(
        (name, next(port.name for port in module.port_details if port.name.lower() == name))
        for name in sorted(canonical)
        if name in names
    )
    evidence = module.ast_refs
    return axi4_lite_model(mapping, evidence)


def recognize_apb4(module: RTLModule) -> ProtocolModel | None:
    names = {port.name.lower() for port in module.port_details}
    required = {"psel", "penable", "pready", "pwrite", "paddr", "pwdata", "pstrb", "prdata", "pslverr"}
    if not required.issubset(names):
        return None
    mapping = tuple(
        (name, next(port.name for port in module.port_details if port.name.lower() == name))
        for name in sorted(required)
    )
    model = apb4_model(mapping, module.ast_refs)
    ports = {port.name.lower(): port for port in module.port_details}
    expected_inputs = {"psel", "penable", "pwrite", "paddr", "pwdata", "pstrb"}
    expected_outputs = {"prdata", "pready", "pslverr"}
    gaps: list[str] = []
    if any(ports[name].direction != "input" for name in expected_inputs):
        gaps.append("APB master-driven signal direction disagrees with slave role")
    if any(ports[name].direction != "output" for name in expected_outputs):
        gaps.append("APB slave response direction disagrees with slave role")
    data_width = ports["pwdata"].width
    if data_width is None or data_width <= 0 or data_width % 8:
        gaps.append("APB data width is unknown or is not byte-addressable")
    elif ports["prdata"].width != data_width:
        gaps.append("APB read and write data widths disagree")
    if data_width is not None and ports["pstrb"].width != data_width // 8:
        gaps.append("PSTRB width does not match PWDATA byte lanes")
    if ports["paddr"].width is None or any(
        ports[name].width != 1 for name in ("psel", "penable", "pready", "pwrite", "pslverr")
    ):
        gaps.append("APB address or control widths are ambiguous")
    return replace(model, unsupported_semantics=tuple(gaps))


def recognize_ahb_lite(module: RTLModule) -> ProtocolModel | None:
    names = {port.name.lower() for port in module.port_details}
    required = {"haddr", "htrans", "hwrite", "hready", "hresp", "hsel", "hwdata", "hrdata"}
    if not required.issubset(names):
        return None
    optional = {"hsize", "hburst", "hprot", "hreadyout", "hclk", "hresetn"}
    mapping = tuple(
        (name, next(port.name for port in module.port_details if port.name.lower() == name))
        for name in sorted(required | optional)
        if name in names
    )
    return ahb_lite_model(mapping, module.ast_refs)


def recognize_control_plane(module: RTLModule) -> tuple[ProtocolModel, ...]:
    clock = (
        module.control_domains[0].clock
        if len(module.control_domains) == 1
        else _named_signal(module, ("aclk", "pclk", "hclk", "clk"))
    )
    reset = (
        module.control_domains[0].reset
        if len(module.control_domains) == 1
        else _named_signal(module, ("aresetn", "presetn", "hresetn", "rst_n", "reset_n"))
    )
    return tuple(
        replace(
            protocol,
            signal_directions=tuple(
                (canonical, next(port.direction for port in module.port_details if port.name == signal))
                for canonical, signal in protocol.signal_bindings
            ),
            clock_domain=clock,
            reset_domain=reset,
            unsupported_semantics=tuple(
                dict.fromkeys(
                    (
                        *protocol.unsupported_semantics,
                        *(
                            ("clock/reset domain is ambiguous",)
                            if protocol.name == "APB4" and (clock is None or reset is None)
                            else ()
                        ),
                    )
                )
            ),
        )
        for protocol in (recognize_axi4_lite(module), recognize_apb4(module), recognize_ahb_lite(module))
        if protocol is not None
    )


def _named_signal(module: RTLModule, candidates: tuple[str, ...]) -> str | None:
    names = {port.name.lower(): port.name for port in module.port_details}
    return next((names[name] for name in candidates if name in names), None)


def recognize_control_plane_source(
    source: str, module: str = "top", source_id: str = "rtl"
) -> tuple[ProtocolModel, ...]:
    """Recognize complete control-plane signatures from a bounded RTL source string.

    This intentionally extracts only port identifiers. Direction, widths, and behavior
    remain parser-owned evidence and are not inferred here.
    """

    if len(source) > 1_000_000:
        raise ValueError("RTL source exceeds the recognition input bound")
    port_names = tuple(dict.fromkeys(re.findall(r"\b[A-Za-z_][A-Za-z0-9_]*\b", source)))
    ports = tuple(RTLPort(name=name, direction="unknown") for name in port_names)
    evidence = (EvidenceRef(EvidenceKind.SEMANTIC_MANIFEST, source_id, f"module:{module}:ports"),)
    return recognize_control_plane(RTLModule(module, source=Path(source_id), port_details=ports, ast_refs=evidence))
