"""Deterministic recognition for the first control-plane protocol milestone."""

from __future__ import annotations

import re
from dataclasses import replace
from pathlib import Path

from dv_platform.agent.protocols import (
    ProtocolChannel,
    ProtocolModel,
    ProtocolProfile,
    ahb_lite_model,
    apb4_model,
    axi4_lite_model,
    production_protocol_profiles,
    protocol_profile,
)
from dv_platform.core.models import EvidenceKind, EvidenceRef, ProductionProtocolBinding, RTLModule, RTLPort


def recognize_axi4_lite(module: RTLModule) -> ProtocolModel | None:
    names = {port.name.lower() for port in module.port_details}
    required = {
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
    }
    if not required.issubset(names):
        return None
    canonical = required | {"aclk", "aresetn", "awaddr", "wdata", "wstrb", "bresp", "araddr", "rdata", "rresp"}
    mapping = tuple(
        (name, next(port.name for port in module.port_details if port.name.lower() == name))
        for name in sorted(canonical)
        if name in names
    )
    model = axi4_lite_model(mapping, module.ast_refs)
    ports = {port.name.lower(): port for port in module.port_details}
    expected_inputs = {"awaddr", "awvalid", "wdata", "wstrb", "wvalid", "bready", "araddr", "arvalid", "rready"}
    expected_outputs = {"awready", "wready", "bresp", "bvalid", "arready", "rdata", "rresp", "rvalid"}
    gaps: list[str] = []
    if any(ports[name].direction != "input" for name in expected_inputs):
        gaps.append("AXI4-Lite master-driven signal direction disagrees with slave role")
    if any(ports[name].direction != "output" for name in expected_outputs):
        gaps.append("AXI4-Lite slave response direction disagrees with slave role")
    data_width = ports["wdata"].width
    if data_width is None or data_width <= 0 or data_width % 8 or ports["rdata"].width != data_width:
        gaps.append("AXI4-Lite data widths are unknown, unequal, or not byte-addressable")
    if data_width is not None and ports["wstrb"].width != data_width // 8:
        gaps.append("WSTRB width does not match WDATA byte lanes")
    if ports["awaddr"].width is None or ports["araddr"].width != ports["awaddr"].width:
        gaps.append("AXI4-Lite address widths are unknown or unequal")
    if any(
        ports[name].width not in {None, 1}
        for name in (
            "awvalid",
            "awready",
            "wvalid",
            "wready",
            "bvalid",
            "bready",
            "arvalid",
            "arready",
            "rvalid",
            "rready",
        )
    ):
        gaps.append("AXI4-Lite handshake widths are ambiguous")
    if ports["bresp"].width != 2 or ports["rresp"].width != 2:
        gaps.append("AXI4-Lite response widths are not two bits")
    return replace(model, unsupported_semantics=tuple(gaps))


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
    # The normalized RTL model uses ``None`` for an unpacked scalar and ``1``
    # when the frontend reports an explicit one-bit packed range.  Both forms
    # are unambiguous scalar controls.
    if ports["paddr"].width is None or any(
        ports[name].width not in {None, 1} for name in ("psel", "penable", "pready", "pwrite", "pslverr")
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
    model = ahb_lite_model(mapping, module.ast_refs)
    ports = {port.name.lower(): port for port in module.port_details}
    expected_inputs = {"haddr", "htrans", "hwrite", "hready", "hsel", "hwdata"}
    expected_outputs = {"hrdata", "hresp"}
    gaps: list[str] = []
    if "hreadyout" not in ports:
        gaps.append("bounded AHB-Lite slave profile requires HREADYOUT")
    else:
        expected_outputs.add("hreadyout")
    if any(ports[name].direction != "input" for name in expected_inputs):
        gaps.append("AHB-Lite master-driven signal direction disagrees with slave role")
    if any(ports[name].direction != "output" for name in expected_outputs):
        gaps.append("AHB-Lite slave response direction disagrees with slave role")
    data_width = ports["hwdata"].width
    if data_width is None or data_width <= 0 or data_width % 8 or ports["hrdata"].width != data_width:
        gaps.append("AHB-Lite data widths are unknown, unequal, or not byte-addressable")
    if ports["haddr"].width is None or ports["htrans"].width != 2:
        gaps.append("AHB-Lite address width is unknown or HTRANS is not two bits")
    controls = ("hwrite", "hready", "hresp", "hsel") + (("hreadyout",) if "hreadyout" in ports else ())
    if any(ports[name].width not in {None, 1} for name in controls):
        gaps.append("AHB-Lite control widths are ambiguous")
    return replace(model, unsupported_semantics=tuple(gaps))


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
                            if protocol.name in {"APB4", "AXI4-Lite", "AHB-Lite"} and (clock is None or reset is None)
                            else ()
                        ),
                    )
                )
            ),
        )
        for protocol in (recognize_axi4_lite(module), recognize_apb4(module), recognize_ahb_lite(module))
        if protocol is not None
    )


def recognize_protocol_profile(
    module: RTLModule,
    profile: ProtocolProfile | str,
    *,
    aliases: tuple[tuple[str, str], ...] = (),
    instance_id: str | None = None,
    role: str | None = None,
) -> ProtocolModel | None:
    """Bind one complete profile instance without fuzzy signal-name guessing.

    With no aliases, only exact canonical names or a single common prefix are
    accepted.  Explicit aliases are all-or-nothing for required signals.  This
    makes partial interfaces and collisions fail closed.
    """

    selected = protocol_profile(profile) if isinstance(profile, str) else profile
    selected.validate()
    ports = {port.name.lower(): port for port in module.port_details}
    required = tuple(signal for signal in selected.signals if not signal.optional)
    alias_map = dict(aliases)
    unknown_aliases = set(alias_map) - {signal.name for signal in selected.signals}
    if unknown_aliases or len(alias_map.values()) != len(set(alias_map.values())):
        raise ValueError("protocol aliases must name unique canonical profile signals")
    matches = _profile_binding_matches(selected, ports, alias_map, bool(aliases))
    if not matches:
        return None
    if len(matches) > 1 and instance_id is None:
        raise ValueError(f"multiple {selected.protocol} instances require an explicit instance_id or aliases")
    prefix, bindings = matches[0]
    bound_ports = {canonical: ports[physical.lower()] for canonical, physical in bindings}
    role_pairs = _role_pairs(selected.roles)
    role = _profile_role(role, role_pairs, required, bound_ports)
    if role not in selected.roles:
        return None
    manager_input = dict(role_pairs)[role]
    gaps = [
        f"{signal.name} direction disagrees with {role} role"
        for signal in required
        if bound_ports[signal.name].direction not in {"unknown", _expected_direction(signal.direction, manager_input)}
    ]
    gaps.extend(_width_gaps(selected, bound_ports))
    channels = _profile_channels(selected, bound_ports, module.ast_refs)
    domain = module.control_domains[0] if len(module.control_domains) == 1 else None
    identity = instance_id or prefix.rstrip("_") or selected.profile_id
    return ProtocolModel(
        name=selected.protocol,
        version=selected.specification_version,
        channels=channels,
        signal_bindings=bindings,
        signal_directions=tuple((name, port.direction) for name, port in bound_ports.items()),
        clock_domain=domain.clock if domain else _named_signal(module, (f"{prefix}aclk", f"{prefix}clk", "clk")),
        reset_domain=domain.reset
        if domain
        else _named_signal(module, (f"{prefix}aresetn", f"{prefix}reset_n", "reset_n")),
        ordering_rules=(selected.ordering_policy,),
        response_rules=selected.completion_rules,
        error_behavior=selected.error_policy,
        confidence="explicit_alias" if aliases else "canonical_signature",
        unsupported_semantics=tuple((*selected.unsupported_semantics, *gaps)),
        evidence_refs=module.ast_refs,
        profile_id=selected.profile_id,
        instance_id=f"{module.name}:{identity}",
        role=role,
        maximum_burst_length=selected.maximum_burst_length,
        maximum_outstanding=selected.maximum_outstanding,
        timeout_cycles=selected.timeout_cycles,
        scoreboard_keys=selected.scoreboard_keys,
        coverage_bins=selected.coverage_bins,
        formal_properties=selected.formal_properties,
        result_traces=selected.result_traces,
    )


def _profile_binding_matches(selected, ports, alias_map, aliases: bool):
    if aliases:
        prefixes = ("",)
    else:
        required = tuple(signal for signal in selected.signals if not signal.optional)
        anchor = required[0].name.lower()
        prefixes = tuple(dict.fromkeys(name[: -len(anchor)] for name in ports if name.endswith(anchor)))
    matches: list[tuple[str, tuple[tuple[str, str], ...]]] = []
    for prefix in prefixes:
        candidate: list[tuple[str, str]] = []
        for signal in selected.signals:
            physical = alias_map.get(signal.name, f"{prefix}{signal.name}")
            port = ports.get(physical.lower())
            if port is None:
                if signal.optional:
                    continue
                break
            candidate.append((signal.name, port.name))
        else:
            matches.append((prefix, tuple(candidate)))
    return matches


def _profile_role(role, role_pairs, required, bound_ports):
    if role is not None:
        return role
    consistent = tuple(
        candidate
        for candidate, manager_input in role_pairs
        if all(
            bound_ports[signal.name].direction in {"unknown", _expected_direction(signal.direction, manager_input)}
            for signal in required
        )
    )
    return consistent[0] if len(consistent) == 1 else None


def _profile_channels(selected, bound_ports, evidence_refs):
    channel_rules = _channel_rules(selected.profile_id)
    return tuple(
        ProtocolChannel(
            name=channel,
            signals=tuple(
                signal.name for signal in selected.signals if signal.channel == channel and signal.name in bound_ports
            ),
            direction="independent",
            transfer_condition=channel_rules.get(
                channel, selected.acceptance_rules[0] if selected.acceptance_rules else ""
            ),
            evidence_refs=evidence_refs,
            payload_fields=tuple(
                signal.name
                for signal in selected.signals
                if signal.channel == channel
                and signal.name in bound_ports
                and not signal.name.endswith(("valid", "ready"))
            ),
            completion_condition=next(iter(selected.completion_rules), None),
        )
        for channel in selected.channels
    )


def recognize_production_protocols(module: RTLModule) -> tuple[ProtocolModel, ...]:
    """Recognize complete canonical instances from every production profile."""

    models: list[ProtocolModel] = []
    for profile in production_protocol_profiles():
        try:
            model = recognize_protocol_profile(module, profile)
        except ValueError as exc:
            if "multiple" not in str(exc):
                raise
            continue
        if model is not None:
            models.append(model)
    # Full AXI contains the AXI4-Lite subset; report only the most specific one.
    if any(model.profile_id == "axi4-1.0" for model in models):
        models = [model for model in models if model.profile_id != "axi4-lite-1.0"]
    return tuple(models)


def recognize_protocols(
    module: RTLModule, bindings: tuple[ProductionProtocolBinding, ...] = ()
) -> tuple[ProtocolModel, ...]:
    """Recognize qualified legacy profiles plus non-duplicated v1 profiles."""

    legacy = recognize_control_plane(module)
    module_names = {module.name, module.original_name or module.name}
    selected = tuple(binding for binding in bindings if binding.module in module_names)
    configured: list[ProtocolModel] = []
    for binding in selected:
        model = recognize_protocol_profile(
            module,
            binding.profile_id,
            aliases=binding.aliases,
            instance_id=binding.instance_id,
            role=binding.role,
        )
        if model is None:
            raise ValueError(
                f"configured protocol binding is incomplete or inconsistent: {binding.module}.{binding.instance_id}"
            )
        configured.append(model)
    explicitly_bound_profiles = {binding.profile_id for binding in selected}
    explicitly_bound_signals = {physical for model in configured for _canonical, physical in model.signal_bindings}
    broad = tuple(
        model
        for model in recognize_production_protocols(module)
        if model.profile_id != "axi4-lite-1.0"
        and model.profile_id not in explicitly_bound_profiles
        and explicitly_bound_signals.isdisjoint(physical for _canonical, physical in model.signal_bindings)
    )
    return (*legacy, *configured, *broad)


def _role_pairs(roles: tuple[str, ...]) -> tuple[tuple[str, bool], ...]:
    manager_names = {"manager", "host", "source"}
    return tuple((role, role in manager_names) for role in roles)


def _expected_direction(profile_direction: str, manager_role: bool) -> str:
    manager_drives = profile_direction == "manager_to_subordinate"
    return "input" if manager_drives != manager_role else "output"


def _width_gaps(profile: ProtocolProfile, ports: dict[str, RTLPort]) -> tuple[str, ...]:
    gaps: list[str] = []
    symbolic: dict[str, int] = {}
    for signal in profile.signals:
        port = ports.get(signal.name)
        if port is None:
            continue
        if isinstance(signal.width, int) and port.width not in {None, signal.width}:
            gaps.append(f"{signal.name} width must be {signal.width}")
        elif isinstance(signal.width, str) and "/" not in signal.width and port.width is not None:
            previous = symbolic.setdefault(signal.width, port.width)
            if previous != port.width:
                gaps.append(f"{signal.name} width disagrees with {signal.width}")
    return tuple(gaps)


def _channel_rules(profile_id: str) -> dict[str, str]:
    if profile_id.startswith("axi4"):
        return {channel: f"{channel}VALID && {channel}READY" for channel in ("AW", "W", "B", "AR", "R")}
    if profile_id.startswith("tilelink"):
        return {channel: f"{channel.lower()}_valid && {channel.lower()}_ready" for channel in ("A", "D")}
    return {}


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
