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
    required = {"psel", "penable", "pready", "pwrite", "paddr", "pwdata", "prdata", "pslverr"}
    if not required.issubset(names):
        return None
    mapping = tuple(
        (name, next(port.name for port in module.port_details if port.name.lower() == name))
        for name in sorted(required)
    )
    return apb4_model(mapping, module.ast_refs)


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
