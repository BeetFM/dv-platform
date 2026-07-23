# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Verilator XML execution and normalization helpers."""

from __future__ import annotations

import re
from xml.etree.ElementTree import Element

from dv_platform.core.models import (
    EvidenceRef,
    RTLAssignment,
    RTLConnection,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLInstance,
    RTLMemory,
    RTLMemoryAccess,
    RTLProceduralBlock,
)

VERILATOR_MIN_TESTED_MAJOR = 5
VERILATOR_MAX_TESTED_MAJOR = 5


def _scoped_instance_elements(
    module_element: Element,
) -> tuple[tuple[Element, str], ...]:
    result: list[tuple[Element, str]] = []

    def visit(element: Element, scope: str = "") -> None:
        tag = _local_name(element.tag)
        local_scope = scope
        if tag in {"begin", "genfor", "genif", "generate", "scope"}:
            scope_name = element.attrib.get("name") or element.attrib.get("origName")
            if scope_name and not scope_name.startswith("unnamedblk"):
                local_scope = (
                    scope_name
                    if not scope or scope_name.startswith(f"{scope}[") or scope_name.startswith(f"{scope}.")
                    else f"{scope}.{scope_name}"
                )
        if tag in {"instance", "cell"}:
            name = element.attrib.get("name") or element.attrib.get("origName")
            if name:
                hierarchical_name = (
                    name
                    if not local_scope or name.startswith((f"{local_scope}.", f"{local_scope}["))
                    else f"{local_scope}.{name}"
                )
                result.append((element, hierarchical_name))
            return
        for child in list(element):
            visit(child, local_scope)

    for child in list(module_element):
        visit(child)
    return tuple(result)


def _instance_module_name(element: Element) -> str | None:
    return (
        element.attrib.get("moduleName")
        or element.attrib.get("modulename")
        or element.attrib.get("submodname")
        or element.attrib.get("dtypeName")
        or element.attrib.get("defName")
    )


def _original_module_name(root: Element | None, elaborated_name: str | None) -> str | None:
    if root is None or elaborated_name is None:
        return None
    return next(
        (
            element.attrib.get("origName")
            for element in root.iter()
            if _local_name(element.tag) == "module"
            and element.attrib.get("name") == elaborated_name
            and element.attrib.get("origName")
        ),
        None,
    )


def _instance_connections(
    element: Element,
    root: Element | None = None,
) -> tuple[RTLConnection, ...]:
    connections: list[RTLConnection] = []
    for port in list(element):
        if _local_name(port.tag) != "port":
            continue
        port_name = port.attrib.get("name") or port.attrib.get("origName")
        if not port_name:
            continue
        expression_element = next(iter(port), None)
        expression = _expression_from_element(expression_element, root=root) if expression_element is not None else None
        direction = port.attrib.get("direction") or port.attrib.get("dir")
        direction = {"in": "input", "out": "output"}.get(str(direction), direction)
        connections.append(
            RTLConnection(
                port_name=port_name,
                direction=direction,
                signal_refs=_expression_signal_refs(expression) if expression is not None else (),
                expression=expression,
                source_location=_source_location(port),
            )
        )
    return tuple(connections)


def _generate_scopes(
    module_element: Element,
    instances: tuple[RTLInstance, ...],
    root: Element | None = None,
) -> tuple[RTLGenerateScope, ...]:
    scopes: dict[str, RTLGenerateScope] = {}
    for element in module_element.iter():
        tag = _local_name(element.tag)
        if tag not in {"begin", "genfor", "genif", "generate", "scope"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        if not name or name.startswith("unnamedblk"):
            continue
        first_child = list(element)[0] if list(element) else None
        scopes.setdefault(
            name,
            RTLGenerateScope(
                scope_id=name,
                name=name,
                kind=tag,
                source_location=_source_location(element),
                instance_names=tuple(
                    instance.name
                    for instance in instances
                    if instance.name.startswith((f"{name}.", f"{name}__DOT__", f"{name}["))
                ),
                condition=(
                    _expression_from_element(first_child, root=root)
                    if tag in {"genif", "genfor"} and first_child is not None
                    else None
                ),
                selected=(
                    element.attrib.get("selected") == "true"
                    if element.attrib.get("selected") in {"true", "false"}
                    else None
                ),
                iteration_index=_generate_iteration_index(name),
            ),
        )
    for instance in instances:
        separator = "__DOT__" if "__DOT__" in instance.name else "." if "." in instance.name else None
        if separator is None:
            continue
        name = instance.name.split(separator, 1)[0]
        existing = scopes.get(name)
        members = tuple(
            item.name for item in instances if item.name.startswith((f"{name}.", f"{name}__DOT__", f"{name}["))
        )
        scopes[name] = RTLGenerateScope(
            scope_id=existing.scope_id if existing is not None else name,
            name=name,
            kind=existing.kind if existing is not None else "elaborated_scope",
            source_location=existing.source_location if existing is not None else instance.source_location,
            instance_names=members,
            condition=existing.condition if existing is not None else None,
            selected=existing.selected if existing is not None else True,
            iteration_index=(
                existing.iteration_index if existing is not None else _generate_iteration_index(instance.name)
            ),
        )
    return tuple(scopes[name] for name in sorted(scopes))


def _generate_iteration_index(name: str) -> int | None:
    match = re.search(r"\[(\d+)\]", name)
    return int(match.group(1)) if match else None


def _imports(module_element: Element) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            name
            for element in module_element.iter()
            if _local_name(element.tag) in {"import", "packageimport", "imported"}
            and (name := element.attrib.get("name") or element.attrib.get("package")) is not None
        )
    )


def _element_summaries(module_element: Element, tags: set[str]) -> tuple[str, ...]:
    summaries: list[str] = []
    for element in _module_child_elements(module_element, tags):
        tag = _local_name(element.tag)
        summaries.append(_element_summary(tag, element))
    return tuple(dict.fromkeys(summaries))


def _assignment_details(
    module_element: Element,
    root: Element | None = None,
) -> tuple[RTLAssignment, ...]:
    assignments: list[RTLAssignment] = []
    for element in module_element.iter():
        if element is module_element or _local_name(element.tag) not in {"assign", "assigndly", "contassign"}:
            continue
        tag = _local_name(element.tag)
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = _source_location(element)
        expressions = _child_expressions(element, root)
        lhs_signals, rhs_signals = _assignment_signal_refs(expressions)
        assignments.append(
            RTLAssignment(
                kind=tag,
                name=name,
                source_location=source_location,
                summary=_element_summary(tag, element),
                lhs_signals=lhs_signals,
                rhs_signals=rhs_signals,
                expressions=expressions,
            )
        )
    return tuple(assignments)


def _module_child_elements(module_element: Element, tags: set[str]) -> tuple[Element, ...]:
    return tuple(child for child in list(module_element) if _local_name(child.tag) in tags)


def _child_expressions(
    element: Element,
    root: Element | None = None,
) -> tuple[RTLExpression, ...]:
    return tuple(_expression_from_element(child, root=root) for child in list(element))


def _expression_from_element(
    element: Element,
    root: Element | None = None,
    depth: int = 0,
    max_depth: int = 32,
) -> RTLExpression:
    kind = _local_name(element.tag)
    if kind == "case":
        constants = tuple(
            (_expression_value(item, _local_name(item.tag)) or "").lower()
            for item in element.iter()
            if _local_name(item.tag) in {"const", "constint", "constant"}
        )
        if any("z" in item for item in constants):
            kind = "casez"
        elif any("x" in item for item in constants):
            kind = "casex"
    children: tuple[RTLExpression, ...] = ()
    if depth < max_depth:
        children = tuple(
            _expression_from_element(child, root=root, depth=depth + 1, max_depth=max_depth) for child in list(element)
        )
    dtype_id = element.attrib.get("dtype_id")
    width, signed = _expression_type(root, dtype_id, element)
    return RTLExpression(
        kind=kind,
        name=element.attrib.get("name") or element.attrib.get("origName"),
        value=_expression_value(element, kind),
        dtype_id=dtype_id,
        source_location=_source_location(element),
        children=children,
        width=width,
        signed=signed,
        cast_kind=_cast_kind(element, kind),
    )


def _expression_value(element: Element, kind: str) -> str | None:
    for key in ("value", "num", "text", "string"):
        value = element.attrib.get(key)
        if value is not None:
            return value
    if kind in {"const", "constint", "constant"}:
        value = element.attrib.get("name")
        if value is not None:
            return value
    text = (element.text or "").strip()
    return text or None


def _assignment_signal_refs(expressions: tuple[RTLExpression, ...]) -> tuple[tuple[str, ...], tuple[str, ...]]:
    if not expressions:
        return (), ()
    lhs = _written_signal_refs(expressions[-1])
    rhs = tuple(dict.fromkeys(ref for expression in expressions[:-1] for ref in _expression_signal_refs(expression)))
    return lhs, rhs


def _expression_signal_refs(expression: RTLExpression) -> tuple[str, ...]:
    refs: list[str] = []
    if expression.name is not None and _looks_like_signal_ref(expression):
        refs.append(expression.name)
    for child in expression.children:
        refs.extend(_expression_signal_refs(child))
    return tuple(refs)


def _looks_like_signal_ref(expression: RTLExpression) -> bool:
    kind = expression.kind.lower()
    if kind in {"varref", "ref", "sel", "arraysel", "bitsel"}:
        return expression.name is not None
    return kind.endswith("ref") and expression.name is not None


def _control_domains_and_blocks(
    module_element: Element,
    root: Element | None = None,
) -> tuple[tuple[RTLControlDomain, ...], tuple[RTLProceduralBlock, ...]]:
    raw_blocks: list[Element] = []
    for element in module_element.iter():
        if element is not module_element and _local_name(element.tag) in {
            "always",
            "alwaysff",
            "alwayscomb",
            "alwayslat",
            "initial",
        }:
            raw_blocks.append(element)

    domains: list[RTLControlDomain] = []
    domain_keys: dict[tuple[object, ...], str] = {}
    block_domains: dict[int, str] = {}
    for element in raw_blocks:
        spec = _control_domain_spec(element)
        if spec is None:
            continue
        key = (
            spec.clock,
            spec.clock_edge,
            spec.reset,
            spec.reset_edge,
            spec.reset_active_low,
            spec.asynchronous_reset,
        )
        domain_id = domain_keys.get(key)
        if domain_id is None:
            domain_id = f"domain_{len(domains) + 1}"
            domain_keys[key] = domain_id
            domains.append(
                RTLControlDomain(
                    domain_id=domain_id,
                    clock=spec.clock,
                    clock_edge=spec.clock_edge,
                    reset=spec.reset,
                    reset_edge=spec.reset_edge,
                    reset_active_low=spec.reset_active_low,
                    asynchronous_reset=spec.asynchronous_reset,
                    source_location=spec.source_location,
                )
            )
        block_domains[id(element)] = domain_id
    return tuple(domains), _procedural_block_details(module_element, block_domains, root)


def _control_domain_spec(element: Element) -> RTLControlDomain | None:
    edges: dict[str, str] = {}
    for item in element.iter():
        if _local_name(item.tag) != "senitem":
            continue
        signal = next(
            (
                child.attrib.get("name") or child.attrib.get("origName")
                for child in item.iter()
                if _local_name(child.tag) == "varref"
            ),
            None,
        )
        if signal:
            edges[signal] = str(item.attrib.get("edgeType", "POS")).lower()
    if not edges:
        return None

    first_if = next((item for item in element.iter() if _local_name(item.tag) == "if"), None)
    condition = list(first_if)[0] if first_if is not None and list(first_if) else None
    condition_signal = _first_signal_ref(_expression_from_element(condition)) if condition is not None else None
    reset = condition_signal if condition_signal in edges and len(edges) > 1 else None
    clock_candidates = tuple(signal for signal in edges if signal != reset)
    if len(clock_candidates) != 1:
        return None
    clock = clock_candidates[0]
    if (
        reset is None
        and condition_signal is not None
        and condition_signal != clock
        and _looks_like_reset(condition_signal)
    ):
        reset = condition_signal
    reset_edge = edges.get(reset) if reset is not None else None
    condition_kind = _local_name(condition.tag) if condition is not None else ""
    reset_active_low = None
    if reset is not None:
        reset_active_low = condition_kind in {"not", "lognot"} or reset_edge == "neg"
        if reset_edge is None and condition_kind not in {"not", "lognot"}:
            reset_active_low = _reset_active_low(reset)
    return RTLControlDomain(
        domain_id="",
        clock=clock,
        clock_edge=edges[clock] or "pos",
        reset=reset,
        reset_edge=reset_edge,
        reset_active_low=reset_active_low,
        asynchronous_reset=reset is not None and reset in edges,
        source_location=_source_location(element),
    )


def _procedural_block_details(
    module_element: Element,
    block_domains: dict[int, str] | None = None,
    root: Element | None = None,
) -> tuple[RTLProceduralBlock, ...]:
    blocks: list[RTLProceduralBlock] = []
    seen: set[tuple[str, str | None, str | None]] = set()
    for element in module_element.iter():
        if element is module_element:
            continue
        tag = _local_name(element.tag)
        if tag not in {"always", "alwaysff", "alwayscomb", "alwayslat", "initial"}:
            continue
        name = element.attrib.get("name") or element.attrib.get("origName")
        source_location = _source_location(element)
        key = (tag, name, source_location)
        if key in seen:
            continue
        seen.add(key)
        expressions = _child_expressions(element, root)
        blocks.append(
            RTLProceduralBlock(
                kind=tag,
                name=name,
                source_location=source_location,
                summary=_element_summary(tag, element),
                signal_refs=tuple(
                    dict.fromkeys(ref for expression in expressions for ref in _expression_signal_refs(expression))
                ),
                expressions=expressions,
                branches=_branch_details(expressions),
                patterns=_procedural_patterns(expressions),
                domain_id=(block_domains or {}).get(id(element)),
            )
        )
    return tuple(blocks)


def _memory_accesses(
    module_name: str,
    memories: tuple[RTLMemory, ...],
    assignments: tuple[RTLAssignment, ...],
    blocks: tuple[RTLProceduralBlock, ...],
    ast_refs: tuple[EvidenceRef, ...],
) -> tuple[RTLMemoryAccess, ...]:
    memory_names = {memory.name for memory in memories}
    if not memory_names:
        return ()
    raw: list[tuple[str, str, tuple[str, ...], tuple[str, ...], tuple[str, ...], str | None, bool, str | None]] = []
    for assignment in assignments:
        if assignment.kind not in {"continuous", "contassign"}:
            continue
        raw.extend(
            _memory_accesses_from_assignment(
                assignment.expressions,
                memory_names,
                (),
                None,
                False,
                assignment.source_location,
            )
        )
    for block in blocks:
        for expression in block.expressions:
            raw.extend(
                _memory_accesses_from_expression(
                    expression,
                    memory_names,
                    (),
                    block.domain_id,
                    block.domain_id is not None,
                )
            )
    seen: set[tuple[object, ...]] = set()
    accesses: list[RTLMemoryAccess] = []
    for memory, kind, addresses, data, enables, domain_id, synchronous, location in raw:
        key = (memory, kind, addresses, data, enables, domain_id, location)
        if key in seen:
            continue
        seen.add(key)
        index = 1 + sum(1 for access in accesses if access.memory == memory and access.kind == kind)
        evidence = tuple(
            ref
            for ref in ast_refs
            if ref.locator.split("@", 1)[0].startswith(
                (f"procedure:{module_name}.", f"assignment:{module_name}.", f"semantic-feature:{module_name}.")
            )
        )
        accesses.append(
            RTLMemoryAccess(
                access_id=f"{module_name}:memory:{memory}:{kind}:{index}",
                memory=memory,
                kind=kind,
                address_signals=addresses,
                data_signals=data,
                enable_signals=enables,
                domain_id=domain_id,
                synchronous=synchronous,
                source_location=location,
                evidence_refs=evidence,
            )
        )
    return tuple(accesses)
