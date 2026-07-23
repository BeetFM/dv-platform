# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

from dataclasses import replace
from xml.etree.ElementTree import Element

from dv_platform.core.models import (
    EvidenceRef,
    ProtocolProfile,
    RTLBranch,
    RTLCDCPath,
    RTLControlDomain,
    RTLExpression,
    RTLMemory,
    RTLMemoryAccess,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProperty,
    RTLProtocol,
)

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def _memory_accesses_from_expression(
    expression: RTLExpression,
    memory_names: set[str],
    controls: tuple[str, ...],
    domain_id: str | None,
    synchronous: bool,
) -> tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None], ...]:
    if expression.kind in {"assign", "assigndly"}:
        return _memory_accesses_from_assignment(
            expression.children,
            memory_names,
            controls,
            domain_id,
            synchronous,
            expression.source_location,
        )
    if expression.kind == "if" and expression.children:
        condition_refs = _expression_signal_refs(expression.children[0])
        nested_controls = tuple(dict.fromkeys((*controls, *condition_refs)))
        return tuple(
            access
            for child in expression.children[1:]
            for access in _memory_accesses_from_expression(
                child,
                memory_names,
                nested_controls,
                domain_id,
                synchronous,
            )
        )
    selected = _memory_selection(expression, memory_names)
    accesses: list[
        tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]
    ] = []
    if selected is not None:
        memory, addresses = selected
        accesses.append((memory, "read", addresses, (), controls, domain_id, synchronous, expression.source_location))
        return tuple(accesses)
    for child in expression.children:
        accesses.extend(_memory_accesses_from_expression(child, memory_names, controls, domain_id, synchronous))
    return tuple(accesses)


def _memory_accesses_from_assignment(
    expressions: tuple[RTLExpression, ...],
    memory_names: set[str],
    controls: tuple[str, ...],
    domain_id: str | None,
    synchronous: bool,
    source_location: str | None,
) -> tuple[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None], ...]:
    if len(expressions) < 2:
        return ()
    rhs = expressions[:-1]
    lhs = expressions[-1]
    accesses: list[
        tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]
    ] = []
    selected_lhs = _memory_selection(lhs, memory_names)
    if selected_lhs is not None:
        memory, addresses = selected_lhs
        rhs_refs = tuple(dict.fromkeys(ref for expression in rhs for ref in _expression_signal_refs(expression)))
        data = tuple(
            ref for ref in rhs_refs if ref not in memory_names and ref not in addresses and ref not in controls
        )
        accesses.append((memory, "write", addresses, data, controls, domain_id, synchronous, source_location))
    read_destinations = tuple(
        ref for ref in _expression_signal_refs(lhs) if ref not in memory_names and ref not in controls
    )
    for expression in rhs:
        expression_accesses = _memory_accesses_from_expression(
            expression, memory_names, controls, domain_id, synchronous
        )
        if selected_lhs is None and read_destinations:
            expression_accesses = tuple(
                (
                    memory,
                    kind,
                    addresses,
                    read_destinations if kind == "read" and not data else data,
                    enables,
                    access_domain,
                    access_synchronous,
                    location,
                )
                for memory, kind, addresses, data, enables, access_domain, access_synchronous, location in expression_accesses
            )
        accesses.extend(expression_accesses)
    if selected_lhs is None:
        accesses.extend(_memory_accesses_from_expression(lhs, memory_names, controls, domain_id, synchronous))
    return tuple(accesses)


def _memory_selection(expression: RTLExpression, memory_names: set[str]) -> tuple[str, tuple[str, ...]] | None:
    if expression.kind not in {"arraysel", "arrayselect"} or not expression.children:
        return None
    base_refs = _expression_signal_refs(expression.children[0])
    memory = next((name for name in base_refs if name in memory_names), None)
    if memory is None:
        return None
    addresses = tuple(dict.fromkeys(ref for child in expression.children[1:] for ref in _expression_signal_refs(child)))
    return memory, addresses


def _memories_with_access_policy(
    memories: tuple[RTLMemory, ...],
    accesses: tuple[RTLMemoryAccess, ...],
) -> tuple[RTLMemory, ...]:
    updated: list[RTLMemory] = []
    for memory in memories:
        reads = tuple(access for access in accesses if access.memory == memory.name and access.kind == "read")
        writes = tuple(access for access in accesses if access.memory == memory.name and access.kind == "write")
        policy = "not_applicable" if not reads or not writes else "unknown"
        updated.append(replace(memory, read_during_write=policy))
    return tuple(updated)


def _cdc_paths(
    module_name: str,
    blocks: tuple[RTLProceduralBlock, ...],
    domains: tuple[RTLControlDomain, ...],
    ast_refs: tuple[EvidenceRef, ...],
    ports: tuple[RTLPort, ...] = (),
) -> tuple[RTLCDCPath, ...]:
    domain_by_id = {domain.domain_id: domain for domain in domains}
    flows: dict[str, tuple[set[str], set[str], tuple[tuple[str, tuple[str, ...]], ...]]] = {}
    for block in blocks:
        if block.domain_id is None:
            continue
        writes: set[str] = set()
        reads: set[str] = set()
        block_pairs: list[tuple[str, tuple[str, ...]]] = []
        for expression in block.expressions:
            _collect_signal_flow(expression, writes, reads, block_pairs)
        existing_writes, existing_reads, existing_pairs = flows.get(block.domain_id, (set(), set(), ()))
        flows[block.domain_id] = (
            existing_writes | writes,
            existing_reads | reads,
            (*existing_pairs, *block_pairs),
        )

    paths: list[RTLCDCPath] = []
    seen: set[tuple[str, str, str]] = set()
    source_flows = tuple(flows.items())
    written_signals = {signal for writes, _reads, _pairs in flows.values() for signal in writes}
    control_signals = {signal for domain in domains for signal in (domain.clock, domain.reset) if signal is not None}
    external_inputs = {port.name for port in ports if port.direction == "input"} - written_signals - control_signals
    if external_inputs:
        source_flows = (*source_flows, ("external", (external_inputs, set(), ())))
    for source_domain, (writes, _source_reads, _source_pairs) in source_flows:
        for destination_domain, (_destination_writes, reads, destination_pairs) in flows.items():
            if source_domain == destination_domain:
                continue
            for signal in sorted(writes & reads):
                key = (signal, source_domain, destination_domain)
                if key in seen:
                    continue
                seen.add(key)
                stage_signals = _synchronizer_chain(signal, destination_pairs)
                stages = len(stage_signals)
                source = domain_by_id.get(source_domain)
                destination = domain_by_id.get(destination_domain)
                reset_compatible = (
                    None
                    if source is None or destination is None
                    else source.reset == destination.reset and source.reset_active_low == destination.reset_active_low
                )
                evidence = tuple(
                    ref for ref in ast_refs if ref.locator.split("@", 1)[0].startswith(f"procedure:{module_name}.")
                )
                paths.append(
                    RTLCDCPath(
                        path_id=f"{module_name}:cdc:{signal}:{source_domain}:{destination_domain}",
                        signal=signal,
                        source_domain=source_domain,
                        destination_domain=destination_domain,
                        classification="two_flop" if stages >= 2 else "direct",
                        synchronizer_stages=stages,
                        stage_signals=stage_signals,
                        safe=stages >= 2 and reset_compatible is not False,
                        reset_compatible=reset_compatible,
                        source_location=destination.source_location if destination is not None else None,
                        evidence_refs=evidence,
                    )
                )
    return tuple(paths)


def _collect_signal_flow(
    expression: RTLExpression,
    writes: set[str],
    reads: set[str],
    pairs: list[tuple[str, tuple[str, ...]]],
) -> None:
    if expression.kind in {"assign", "assigndly"} and len(expression.children) >= 2:
        lhs = expression.children[-1]
        rhs = expression.children[:-1]
        lhs_refs = _written_signal_refs(lhs)
        rhs_refs = tuple(dict.fromkeys(ref for item in rhs for ref in _expression_signal_refs(item)))
        writes.update(lhs_refs)
        reads.update(rhs_refs)
        reads.update(ref for ref in _expression_signal_refs(lhs) if ref not in lhs_refs)
        for lhs_ref in lhs_refs:
            pairs.append((lhs_ref, rhs_refs))
        return
    if expression.kind == "sentree":
        return
    if expression.kind == "if" and expression.children:
        reads.update(_expression_signal_refs(expression.children[0]))
        for child in expression.children[1:]:
            _collect_signal_flow(child, writes, reads, pairs)
        return
    for child in expression.children:
        _collect_signal_flow(child, writes, reads, pairs)


def _written_signal_refs(expression: RTLExpression) -> tuple[str, ...]:
    if expression.kind in {"arraysel", "arrayselect", "bitsel", "sel"} and expression.children:
        refs = _expression_signal_refs(expression.children[0])
        return refs[:1]
    refs = _expression_signal_refs(expression)
    return refs[:1]


def _synchronizer_chain(
    signal: str,
    pairs: tuple[tuple[str, tuple[str, ...]], ...],
) -> tuple[str, ...]:
    frontier = {signal}
    visited: set[str] = set()
    chain: list[str] = []
    while frontier:
        next_frontier = sorted(
            {lhs for lhs, rhs in pairs if lhs not in visited and any(source in frontier for source in rhs)}
        )
        if len(next_frontier) != 1:
            break
        chain.append(next_frontier[0])
        visited.update(next_frontier)
        frontier = set(next_frontier)
    return tuple(chain)


def _protocols(
    module_name: str,
    ports: tuple[RTLPort, ...],
    control_domains: tuple[RTLControlDomain, ...],
    ast_refs: tuple[EvidenceRef, ...],
    configured_profiles: tuple[ProtocolProfile, ...],
) -> tuple[RTLProtocol, ...]:
    profiles = (
        ProtocolProfile(name="builtin_ready_valid"),
        *configured_profiles,
    )
    by_name = {port.name: port for port in ports}
    protocols: list[RTLProtocol] = []
    seen: set[tuple[str, str, str]] = set()
    for profile in profiles:
        for valid in ports:
            protocol = _protocol_candidate(module_name, profile, valid, by_name, control_domains, ast_refs, seen)
            if protocol is not None:
                protocols.append(protocol)
    return tuple(protocols)


def _protocol_candidate(module_name, profile, valid, by_name, control_domains, ast_refs, seen):
    if valid.name == profile.valid_suffix.removeprefix("_"):
        prefix = ""
    elif valid.name.endswith(profile.valid_suffix):
        prefix = valid.name.removesuffix(profile.valid_suffix)
    else:
        return None
    ready_name = f"{prefix}{profile.ready_suffix}" if prefix else profile.ready_suffix.removeprefix("_")
    ready = by_name.get(ready_name)
    role = _protocol_role(valid, ready)
    if ready is None or role is None:
        return None
    key = (profile.kind, valid.name, ready.name)
    if key in seen:
        return None
    seen.add(key)
    data_names = tuple(f"{prefix}{suffix}" if prefix else suffix.removeprefix("_") for suffix in profile.data_suffixes)
    data = next(
        (by_name[name] for name in data_names if name in by_name and by_name[name].direction == valid.direction),
        None,
    )
    domain = control_domains[0] if len(control_domains) == 1 else None
    channel_name = prefix or "channel"
    locators = {
        f"port:{module_name}.{valid.name}",
        f"port:{module_name}.{ready.name}",
        *(set() if data is None else {f"port:{module_name}.{data.name}"}),
    }
    return RTLProtocol(
        protocol_id=f"{module_name}:{profile.kind}:{channel_name}",
        kind=profile.kind,
        name=channel_name,
        role=role,
        valid=valid.name,
        ready=ready.name,
        data=data.name if data is not None else None,
        data_width=data.width if data is not None else None,
        clock=domain.clock if domain is not None else None,
        reset=domain.reset if domain is not None else None,
        confidence="configured_profile" if profile.name != "builtin_ready_valid" else "structured_ports",
        profile=profile.name,
        signal_map=tuple(
            (role_name, signal_name)
            for role_name, signal_name in (
                ("valid" if profile.kind == "ready_valid" else "request", valid.name),
                ("ready" if profile.kind == "ready_valid" else "acknowledge", ready.name),
                ("data", data.name if data is not None else None),
            )
            if signal_name is not None
        ),
        evidence_refs=tuple(ref for ref in ast_refs if ref.locator.split("@", 1)[0] in locators),
    )


def _protocol_role(valid, ready):
    if ready is None:
        return None
    if valid.direction == "input" and ready.direction == "output":
        return "sink"
    if valid.direction == "output" and ready.direction == "input":
        return "source"
    return None


def _procedural_patterns(expressions: tuple[RTLExpression, ...]) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    for expression in expressions:
        patterns.extend(_patterns_from_expression(expression, control=None))
    return tuple(dict.fromkeys(patterns))


def _patterns_from_expression(expression: RTLExpression, control: str | None) -> tuple[RTLProceduralPattern, ...]:
    patterns: list[RTLProceduralPattern] = []
    if expression.kind == "if":
        condition = expression.children[0] if expression.children else None
        branch_control = _first_signal_ref(condition) if condition is not None else control
        for child in expression.children[1:]:
            patterns.extend(_patterns_from_expression(child, branch_control))
        return tuple(patterns)
    if expression.kind == "case":
        for child in expression.children:
            patterns.extend(_patterns_from_expression(child, None))
        return tuple(patterns)
    if expression.kind in {"assign", "assigndly"}:
        pattern = _pattern_from_assign(expression, control)
        if pattern is not None:
            patterns.append(pattern)
    for child in expression.children:
        patterns.extend(_patterns_from_expression(child, control))
    return tuple(patterns)


def _branch_details(expressions: tuple[RTLExpression, ...]) -> tuple[RTLBranch, ...]:
    branches: list[RTLBranch] = []
    for expression in expressions:
        if expression.kind == "if" and expression.children:
            branches.append(
                RTLBranch(
                    kind="if",
                    source_location=expression.source_location,
                    condition=expression.children[0],
                    mutually_exclusive=True,
                )
            )
        if expression.kind in {"case", "casez", "casex"} and expression.children:
            selector = expression.children[0]
            for item in expression.children[1:]:
                if item.kind != "caseitem":
                    continue
                labels = item.children[:-1] if item.children else ()
                branches.append(
                    RTLBranch(
                        kind=expression.kind,
                        source_location=item.source_location,
                        condition=selector,
                        labels=labels,
                        is_default=not labels,
                        mutually_exclusive=True if expression.kind == "case" else None,
                    )
                )
        branches.extend(_branch_details(expression.children))
    return tuple(branches)


def _pattern_from_assign(expression: RTLExpression, control: str | None) -> RTLProceduralPattern | None:
    if len(expression.children) < 2:
        return None
    target = _first_signal_ref(expression.children[-1])
    value_expression = expression.children[0]
    if target is None:
        return None
    constant = _constant_value(value_expression)
    if constant is not None and control is not None:
        return RTLProceduralPattern(kind="reset_to_constant", target=target, control=control, value=constant)
    increment_source = _increment_source(target, value_expression)
    if increment_source is not None:
        return RTLProceduralPattern(kind="increment", target=target, control=control, source=increment_source)
    return None


def _first_signal_ref(expression: RTLExpression | None) -> str | None:
    if expression is None:
        return None
    refs = _expression_signal_refs(expression)
    return refs[0] if refs else None


def _constant_value(expression: RTLExpression) -> str | None:
    if expression.kind in {"const", "constint", "constant"}:
        return expression.value
    return None


def _increment_source(target: str, expression: RTLExpression) -> str | None:
    if expression.kind not in {"add", "plus"}:
        return None
    signal_refs = _expression_signal_refs(expression)
    constants = tuple(_constant_value(child) for child in expression.children)
    if target not in signal_refs:
        return None
    if not any(_is_one_constant(value) for value in constants if value is not None):
        return None
    return target


def _is_one_constant(value: str) -> bool:
    normalized = value.lower().replace("&apos;", "'")
    return normalized == "1" or normalized.endswith("'h1") or normalized.endswith("'b1") or normalized.endswith("'d1")


def _matching_element_summaries(module_element: Element, pattern: str) -> tuple[str, ...]:
    summaries: list[str] = []
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if pattern in tag:
            summaries.append(_element_summary(tag, element))
    return tuple(dict.fromkeys(summaries))


def _property_details(
    module_element: Element,
    root: Element,
) -> tuple[RTLProperty, ...]:
    """Normalize property structure and mark unsupported temporal operators explicitly."""

    properties: list[RTLProperty] = []
    for element in module_element.iter():
        tag = _local_name(element.tag)
        if not any(token in tag for token in ("assert", "assume", "cover")):
            continue
        if tag in {"assertion", "assertions", "coverage"}:
            continue
        kind = "cover" if "cover" in tag else "assume" if "assume" in tag else "assert"
        descendant_tags = tuple(_local_name(item.tag) for item in element.iter())
        unsupported = tuple(
            sorted(
                {
                    item
                    for item in descendant_tags
                    if any(
                        token in item
                        for token in (
                            "delay",
                            "repeat",
                            "throughout",
                            "within",
                            "until",
                            "firstmatch",
                        )
                    )
                }
            )
        )
        body_element = next(iter(element), None)
        body = _expression_from_element(body_element, root=root) if body_element is not None else None
        concurrent = "property" in tag or element.attrib.get("concurrent") == "true"
        if body is None and not unsupported and not concurrent:
            # Older Verilator fixture schemas retain only assertion summaries.
            # Preserve compatibility without claiming structured property support.
            continue
        properties.append(
            RTLProperty(
                kind=kind,
                name=element.attrib.get("name") or element.attrib.get("origName"),
                concurrent=concurrent,
                clock=_property_clock(element),
                clock_edge=_property_clock_edge(element),
                body=body,
                source_location=_source_location(element),
                support_status="unsupported" if unsupported or body is None else "normalized",
                unsupported_operators=unsupported,
            )
        )
    return tuple(properties)


def _property_clock(element: Element) -> str | None:
    for item in element.iter():
        edge = str(item.attrib.get("edgeType", item.attrib.get("edge", ""))).lower()
        if "pos" not in edge and "neg" not in edge:
            continue
        return item.attrib.get("name") or item.attrib.get("origName")
    return None
