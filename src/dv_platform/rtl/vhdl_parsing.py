# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Bounded, deterministic VHDL entity and architecture normalization.

This frontend intentionally accepts a small synthesizable VHDL profile.  It is
not a replacement for GHDL elaboration: unsupported or ambiguous source shapes
are rejected so downstream planning cannot promote guessed facts.
"""

from __future__ import annotations

import ast
import hashlib
import re
from pathlib import Path

from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLAssignment,
    RTLClock,
    RTLControlDomain,
    RTLExpression,
    RTLGenerateScope,
    RTLParameter,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLReset,
)

VHDL_NORMALIZER_VERSION = "vhdl-source-normalizer/2"


def _generate_scopes(
    architecture: _Architecture,
    source_file: Path,
    text: str,
    values: dict[str, int],
) -> tuple[RTLGenerateScope, ...]:
    scopes: list[RTLGenerateScope] = []
    pattern = re.compile(
        r"\b(?P<label>[a-z][a-z0-9_]*)\s*:\s*(?:(?:for\s+(?P<index>[a-z][a-z0-9_]*)\s+in\s+(?P<range>.+?))|(?:if\s+(?P<condition>.+?)))\s+generate\b",
        re.IGNORECASE,
    )
    for match in pattern.finditer(architecture.statements):
        location = f"{source_file}:{_line(text, architecture.statements_start + match.start())}"
        if match.group("range") is not None:
            range_match = re.fullmatch(r"(.+?)\s+(to|downto)\s+(.+)", match.group("range").strip(), re.IGNORECASE)
            if range_match is None:
                raise VHDLNormalizationError(f"unsupported VHDL generate range: {match.group('range')}")
            left = _integer_expression(range_match.group(1), values)
            right = _integer_expression(range_match.group(3), values)
            step = 1 if range_match.group(2).lower() == "to" else -1
            if (step == 1 and left > right) or (step == -1 and left < right):
                raise VHDLNormalizationError(f"invalid VHDL generate range: {match.group('range')}")
            for iteration in range(left, right + step, step):
                scopes.append(
                    RTLGenerateScope(
                        f"{match.group('label')}[{iteration}]",
                        match.group("label"),
                        "vhdl_for_generate",
                        location,
                        selected=True,
                        iteration_index=iteration,
                    )
                )
        else:
            condition = " ".join(match.group("condition").split())
            selected = _vhdl_boolean_expression(condition, values)
            scopes.append(
                RTLGenerateScope(
                    match.group("label"),
                    match.group("label"),
                    "vhdl_if_generate",
                    location,
                    condition=RTLExpression("constant", value=str(selected).lower(), width=1),
                    selected=selected,
                )
            )
    return tuple(scopes)


def _vhdl_boolean_expression(expression: str, values: dict[str, int]) -> bool:
    normalized = expression.strip()
    literal = normalized.lower()
    if literal in {"true", "false"}:
        return literal == "true"
    comparison = re.fullmatch(r"(.+?)\s*(=|/=|<=|>=|<|>)\s*(.+)", normalized)
    if comparison is None:
        raise VHDLNormalizationError(f"unsupported VHDL generate condition: {expression}")
    left = _integer_expression(comparison.group(1), values)
    right = _integer_expression(comparison.group(3), values)
    return {
        "=": left == right,
        "/=": left != right,
        "<=": left <= right,
        ">=": left >= right,
        "<": left < right,
        ">": left > right,
    }[comparison.group(2)]


def _clock_details(ports: tuple[RTLPort, ...], architecture: _Architecture) -> tuple[RTLClock, ...]:
    edge_names = {
        match.group(2).lower()
        for match in re.finditer(
            r"\b(rising_edge|falling_edge)\s*\(\s*([a-z][a-z0-9_]*)\s*\)", architecture.statements, re.IGNORECASE
        )
    }
    return tuple(
        RTLClock(
            port.name,
            port.direction,
            port.width,
            port.source_location,
            "vhdl_edge_function" if port.name.lower() in edge_names else "name_heuristic",
            "high" if port.name.lower() in edge_names else "low",
        )
        for port in ports
        if port.direction == "input" and (port.name.lower() in edge_names or _looks_like_clock(port.name))
    )


def _reset_details(ports: tuple[RTLPort, ...], architecture: _Architecture) -> tuple[RTLReset, ...]:
    comparisons = {
        match.group(1).lower(): match.group(2)
        for match in re.finditer(
            r"\bif\s+([a-z][a-z0-9_]*)\s*=\s*'([01])'\s+then",
            architecture.statements,
            re.IGNORECASE,
        )
    }
    return tuple(
        RTLReset(
            port.name,
            port.direction,
            port.width,
            comparisons.get(port.name.lower()) == "0"
            if port.name.lower() in comparisons
            else port.name.lower().endswith("_n"),
            port.source_location,
            "vhdl_reset_branch" if port.name.lower() in comparisons else "name_heuristic",
            "high" if port.name.lower() in comparisons else "low",
        )
        for port in ports
        if port.direction == "input" and _looks_like_reset(port.name)
    )


def _procedural_details(
    architecture: _Architecture,
    source_file: Path,
    text: str,
    clocks: tuple[RTLClock, ...],
    resets: tuple[RTLReset, ...],
) -> tuple[tuple[RTLControlDomain, ...], tuple[RTLProceduralBlock, ...]]:
    domains: list[RTLControlDomain] = []
    blocks: list[RTLProceduralBlock] = []
    process_pattern = re.compile(
        r"(?:\b(?P<label>[a-z][a-z0-9_]*)\s*:\s*)?\bprocess\s*(?:\((?P<sensitivity>.*?)\))?"
        r"(?P<body>.*?)\bend\s+process(?:\s+[a-z][a-z0-9_]*)?\s*;",
        re.IGNORECASE | re.DOTALL,
    )
    for index, match in enumerate(process_pattern.finditer(architecture.statements), start=1):
        body = match.group("body")
        edge = re.search(r"\b(rising_edge|falling_edge)\s*\(\s*([a-z][a-z0-9_]*)\s*\)", body, re.IGNORECASE)
        domain_id = None
        if edge:
            clock = edge.group(2)
            reset = next(
                (item for item in resets if re.search(rf"\b{re.escape(item.name)}\b", body, re.IGNORECASE)),
                None,
            )
            sensitivity = {
                item.strip().lower() for item in (match.group("sensitivity") or "").split(",") if item.strip()
            }
            domain_id = f"domain_{len(domains) + 1}"
            domains.append(
                RTLControlDomain(
                    domain_id=domain_id,
                    clock=clock,
                    clock_edge="pos" if edge.group(1).lower() == "rising_edge" else "neg",
                    reset=reset.name if reset else None,
                    reset_edge="neg" if reset and reset.active_low else "pos" if reset else None,
                    reset_active_low=reset.active_low if reset else None,
                    asynchronous_reset=reset is not None and reset.name.lower() in sensitivity,
                    source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                )
            )
        patterns = _vhdl_procedural_patterns(body)
        signals = tuple(dict.fromkeys(re.findall(r"\b[a-z][a-z0-9_]*\b", body, re.IGNORECASE)))
        label = match.group("label") or f"process_{index}"
        blocks.append(
            RTLProceduralBlock(
                kind="process",
                name=label,
                source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                summary=f"process {label}",
                signal_refs=signals,
                patterns=tuple(patterns),
                domain_id=domain_id,
            )
        )
    # Edge functions outside a process are rejected because the normalized
    # control-domain ownership would be ambiguous.
    if any(clock.classification == "vhdl_edge_function" for clock in clocks) and not blocks:
        raise VHDLNormalizationError(
            f"architecture {architecture.name} contains clock evidence but no parsable process"
        )
    return tuple(domains), tuple(blocks)


def _vhdl_procedural_patterns(body: str) -> list[RTLProceduralPattern]:
    patterns: list[RTLProceduralPattern] = []
    for assignment in re.finditer(r"\b([a-z][a-z0-9_]*)\s*<=\s*([^;]+);", body, re.IGNORECASE):
        target, value = assignment.group(1), " ".join(assignment.group(2).split())
        prefix = body[: assignment.start()]
        guard = re.search(
            r"\bif\s+([a-z][a-z0-9_]*)\s*=\s*'[01]'\s+then\s*$",
            prefix,
            re.IGNORECASE,
        )
        if guard:
            patterns.append(
                RTLProceduralPattern(
                    "reset_to_constant",
                    target,
                    control=guard.group(1),
                    value=value,
                    confidence="parser",
                )
            )
        if re.search(rf"\b{re.escape(target)}\s*\+\s*1\b", value, re.IGNORECASE):
            patterns.append(RTLProceduralPattern("increment", target, value="1", confidence="parser"))
    return patterns


def _concurrent_assignments(
    architecture: _Architecture,
    source_file: Path,
    text: str,
) -> tuple[RTLAssignment, ...]:
    statements = re.sub(
        r"(?:\b[a-z][a-z0-9_]*\s*:\s*)?\bprocess\b.*?\bend\s+process(?:\s+[a-z][a-z0-9_]*)?\s*;",
        lambda match: " " * len(match.group(0)),
        architecture.statements,
        flags=re.IGNORECASE | re.DOTALL,
    )
    assignments = []
    for match in re.finditer(r"\b([a-z][a-z0-9_]*)\s*<=\s*([^;]+);", statements, re.IGNORECASE):
        lhs, rhs = match.group(1), " ".join(match.group(2).split())
        rhs_signals = tuple(
            token
            for token in dict.fromkeys(re.findall(r"\b[a-z][a-z0-9_]*\b", rhs, re.IGNORECASE))
            if token.lower() not in {"not", "and", "or", "xor", "others"}
        )
        assignments.append(
            RTLAssignment(
                kind="continuous",
                source_location=f"{source_file}:{_line(text, architecture.statements_start + match.start())}",
                summary=f"{lhs} <= {rhs}",
                lhs_signals=(lhs,),
                rhs_signals=rhs_signals,
            )
        )
    return tuple(assignments)


def _interface_block(body: str, keyword: str) -> tuple[str, int] | None:
    match = re.search(rf"\b{keyword}\s*\(", body, re.IGNORECASE)
    if match is None:
        return None
    start = match.end()
    depth = 1
    for index in range(start, len(body)):
        if body[index] == "(":
            depth += 1
        elif body[index] == ")":
            depth -= 1
            if depth == 0:
                return body[start:index], start
    raise VHDLNormalizationError(f"unterminated VHDL {keyword} clause")


def _declarations(block: str) -> tuple[tuple[str, int], ...]:
    result: list[tuple[str, int]] = []
    depth = 0
    start = 0
    for index, character in enumerate(block):
        if character == "(":
            depth += 1
        elif character == ")":
            depth -= 1
        elif character == ";" and depth == 0:
            if block[start:index].strip():
                result.append((block[start:index], start))
            start = index + 1
    if block[start:].strip():
        result.append((block[start:], start))
    return tuple(result)


def _integer_expression(expression: str, values: dict[str, int]) -> int:
    normalized = expression.strip().replace("/", "//")
    for name, value in sorted(values.items(), key=lambda item: -len(item[0])):
        normalized = re.sub(rf"\b{re.escape(name)}\b", str(value), normalized, flags=re.IGNORECASE)
    try:
        node = ast.parse(normalized, mode="eval")
    except SyntaxError as error:
        raise VHDLNormalizationError(f"unsupported VHDL integer expression: {expression.strip()}") from error

    def evaluate(item: ast.AST) -> int:
        if isinstance(item, ast.Expression):
            return evaluate(item.body)
        if isinstance(item, ast.Constant) and isinstance(item.value, int) and not isinstance(item.value, bool):
            return item.value
        if isinstance(item, ast.UnaryOp) and isinstance(item.op, (ast.UAdd, ast.USub)):
            value = evaluate(item.operand)
            return value if isinstance(item.op, ast.UAdd) else -value
        if isinstance(item, ast.BinOp) and isinstance(item.op, (ast.Add, ast.Sub, ast.Mult, ast.FloorDiv)):
            left, right = evaluate(item.left), evaluate(item.right)
            if isinstance(item.op, ast.Add):
                return left + right
            if isinstance(item.op, ast.Sub):
                return left - right
            if isinstance(item.op, ast.Mult):
                return left * right
            if right == 0:
                raise VHDLNormalizationError("division by zero in VHDL integer expression")
            return left // right
        raise VHDLNormalizationError(f"unsupported VHDL integer expression: {expression.strip()}")

    return evaluate(node)


def _parameter_override_map(overrides: tuple[str, ...]) -> dict[str, str]:
    result: dict[str, str] = {}
    for override in overrides:
        name, separator, value = override.partition("=")
        if not separator or not name or not value:
            raise VHDLNormalizationError(f"invalid VHDL generic override: {override}")
        key = name.lower()
        if key in result:
            raise VHDLNormalizationError(f"duplicate VHDL generic override: {name}")
        result[key] = value
    return result


def _specialization_id(entity: str, architecture: str, parameters: tuple[RTLParameter, ...]) -> str:
    signature = "\0".join(
        (entity.lower(), architecture.lower(), *(f"{item.name.lower()}={item.default_value}" for item in parameters))
    )
    return hashlib.sha256(signature.encode("utf-8")).hexdigest()[:16]


def _evidence(
    source_file: Path,
    module: str,
    category: str,
    name: str,
    line: int,
    summary: str,
) -> EvidenceRef:
    key = module if category == "module" else f"{module}.{name}"
    return EvidenceRef(EvidenceKind.VHDL_SOURCE, str(source_file), f"{category}:{key}@{source_file}:{line}", summary)


def _strip_comments(text: str) -> str:
    return "\n".join(line.split("--", 1)[0] for line in text.splitlines()) + ("\n" if text.endswith("\n") else "")


def _line(text: str, offset: int) -> int:
    return text.count("\n", 0, max(0, offset)) + 1


def _source_line(source_location: str | None) -> int:
    if source_location is None:
        return 1
    try:
        return int(source_location.rsplit(":", 1)[1])
    except (IndexError, ValueError):
        return 1


def _looks_like_clock(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"clk", "clock"} or lowered.endswith(("_clk", "_clock"))


def _looks_like_reset(name: str) -> bool:
    lowered = name.lower()
    return lowered in {"rst", "reset", "rst_n", "reset_n"} or lowered.endswith(("_rst", "_reset", "_rst_n", "_reset_n"))
