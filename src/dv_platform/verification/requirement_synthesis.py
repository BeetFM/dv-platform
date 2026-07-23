# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Initial deterministic planner used before agent-backed planning exists."""

from __future__ import annotations

import hashlib
import re
from pathlib import Path

from dv_platform.analysis.docs import EmbeddingProvider, VectorStore, retrieve_chunks, retrieve_chunks_with_vectors
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RequirementConflict,
    RTLExpression,
    RTLModule,
    Severity,
    VerificationClaim,
    VerificationRequirement,
)


def _retrieve_documentation_refs(
    module: RTLModule,
    documentation_chunks: tuple[DocumentationChunk, ...],
    retrieval_index_dir: Path | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    vector_store: VectorStore | None = None,
) -> tuple[EvidenceRef, ...]:
    if not documentation_chunks:
        return ()

    query = " ".join((module.name, *module.ports, *module.parameters, *module.instances))
    results = (
        retrieve_chunks_with_vectors(
            query,
            documentation_chunks,
            retrieval_index_dir,
            limit=3,
            provider=embedding_provider,
            store=vector_store,
        )
        if retrieval_index_dir is not None
        else retrieve_chunks(query, documentation_chunks, limit=3)
    )
    refs: list[EvidenceRef] = []
    for result in results:
        chunk = result.chunk
        query_terms = (module.name, *module.ports, *module.parameters, *module.instances)
        sentences = tuple(
            dict.fromkeys(
                (
                    *_structured_requirement_fragments(chunk.text, query_terms),
                    *_relevant_requirement_sentences(chunk.text, query_terms),
                )
            )
        )
        if not sentences:
            sentences = ((_requirement_summary(chunk.text, query_terms=query_terms), 0, len(chunk.text)),)
        for sentence, local_start, local_end in sentences:
            absolute_start = (chunk.start_offset or 0) + local_start
            absolute_end = (chunk.start_offset or 0) + local_end
            refs.append(
                EvidenceRef(
                    kind=EvidenceKind.DOCUMENT_CHUNK,
                    source_id=str(chunk.source),
                    locator=(
                        f"chunk:{chunk.chunk_id}@{absolute_start}:{absolute_end}"
                        + (f"#{chunk.source_locator}" if chunk.source_locator else "")
                    ),
                    summary=sentence,
                )
            )
    return tuple(refs)


def _merge_imported_requirements(
    module: RTLModule,
    synthesized: tuple[VerificationRequirement, ...],
    imported: tuple[VerificationRequirement, ...],
) -> tuple[VerificationRequirement, ...]:
    scopes = {
        "*",
        "all",
        "global",
        module.name,
        module.original_name or module.name,
        module.elaborated_name or module.name,
    }
    merged = {requirement.requirement_id: requirement for requirement in synthesized}
    for requirement in imported:
        if requirement.scope not in scopes:
            continue
        existing = merged.get(requirement.requirement_id)
        if existing is not None and existing.statement != requirement.statement:
            raise ValueError(
                f"Requirement ID collision for {requirement.requirement_id}: governed and synthesized statements differ"
            )
        merged[requirement.requirement_id] = requirement
    return tuple(merged.values())


def _synthesize_requirements(
    module: RTLModule,
    documentation_refs: tuple[EvidenceRef, ...],
) -> tuple[VerificationRequirement, ...]:
    grouped: dict[str, tuple[str, list[EvidenceRef]]] = {}
    for ref in documentation_refs:
        statement = " ".join((ref.summary or ref.locator).split())
        canonical = _canonical_requirement(statement)
        if not canonical:
            continue
        existing = grouped.get(canonical)
        if existing is None:
            grouped[canonical] = (statement, [ref])
        elif ref not in existing[1]:
            existing[1].append(ref)

    requirements: list[VerificationRequirement] = []
    for canonical, (statement, refs) in sorted(grouped.items()):
        normalized_statement = statement.lower()
        category = (
            "protocol"
            if any(
                protocol.valid.lower() in normalized_statement and protocol.ready.lower() in normalized_statement
                for protocol in module.protocols
            )
            else _requirement_category(statement)
        )
        signals = tuple(port for port in module.ports if _contains_term(statement.lower(), port.lower()))
        expected_value = _requirement_expected_value(statement, category)
        condition = _requirement_condition(module, statement)
        identity = "|".join((module.name, category, ",".join(signals), canonical))
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
        requirements.append(
            VerificationRequirement(
                requirement_id=f"{module.name}:docreq:{digest}",
                scope=module.name,
                statement=statement,
                category=category,
                signals=signals,
                expected_value=expected_value,
                condition=condition,
                confidence="deterministic" if category != "general" and signals else "lexical",
                evidence_refs=tuple(refs),
            )
        )
    return tuple(requirements)


def _find_requirement_conflicts(
    module: RTLModule,
    requirements: tuple[VerificationRequirement, ...],
) -> tuple[RequirementConflict, ...]:
    conflicts: list[RequirementConflict] = []
    for index, left in enumerate(requirements):
        for right in requirements[index + 1 :]:
            if left.category == "general" or left.category != right.category:
                continue
            if not set(left.signals) or set(left.signals) != set(right.signals):
                continue
            if left.condition != right.condition:
                continue
            if left.expected_value is None or right.expected_value is None:
                continue
            if left.expected_value == right.expected_value:
                continue
            requirement_ids = tuple(sorted((left.requirement_id, right.requirement_id)))
            digest = hashlib.sha256("|".join(requirement_ids).encode("utf-8")).hexdigest()[:12]
            conflicts.append(
                RequirementConflict(
                    conflict_id=f"{module.name}:conflict:{digest}",
                    scope=module.name,
                    requirement_ids=requirement_ids,
                    reason=(
                        f"Conflicting {left.category} values for {', '.join(left.signals)}"
                        f" under {left.condition or 'the same condition'}: "
                        f"{left.expected_value} versus {right.expected_value}."
                    ),
                    evidence_refs=tuple(dict.fromkeys((*left.evidence_refs, *right.evidence_refs))),
                )
            )
    return tuple(conflicts)


def _conflict_claim(conflict: RequirementConflict) -> VerificationClaim:
    return VerificationClaim(
        claim_id=f"{conflict.conflict_id}:resolution",
        scope=conflict.scope,
        statement=conflict.reason,
        claim_type=ClaimType.DOCUMENTATION_INTENT,
        severity=Severity.CRITICAL,
        generation_precondition=True,
        status=ClaimStatus.CONTRADICTED,
        evidence_refs=conflict.evidence_refs,
    )


def _conflict_open_question(conflict: RequirementConflict) -> str:
    identifiers = " and ".join(conflict.requirement_ids)
    return f"Resolve {identifiers}: {conflict.reason} Which documented value is authoritative?"


def _requirement_open_questions(
    module: RTLModule,
    requirements: tuple[VerificationRequirement, ...],
) -> tuple[str, ...]:
    questions: list[str] = []
    supported_categories = {"reset", "increment", "hold", "connectivity", "protocol"}
    for requirement in requirements:
        if _checks_for_requirement(module, requirement.statement.lower()):
            continue
        if requirement.category in supported_categories:
            detail = "identify the observable input, output, and expected value"
        else:
            detail = "define observable signals, timing, and pass/fail behavior"
        questions.append(
            f"Requirement {requirement.requirement_id} ({requirement.category}) has no executable check; {detail}."
        )
    return tuple(questions)


def _relevant_requirement_sentences(
    text: str,
    query_terms: tuple[str, ...],
    limit: int = 5,
) -> tuple[tuple[str, int, int], ...]:
    candidates: list[tuple[int, int, str, int, int]] = []
    normalized_terms = tuple(term.lower() for term in query_terms if term)
    start = 0
    for match in re.finditer(r"(?<=[.!?])\s+|\n\s*\n", text):
        raw = text[start : match.start()]
        stripped = raw.strip()
        if stripped:
            local_start = start + len(raw) - len(raw.lstrip())
            local_end = local_start + len(stripped)
            score = sum(1 for term in normalized_terms if _contains_term(stripped.lower(), term))
            candidates.append((score, len(candidates), stripped, local_start, local_end))
        start = match.end()
    raw = text[start:]
    stripped = raw.strip()
    if stripped:
        local_start = start + len(raw) - len(raw.lstrip())
        candidates.append(
            (
                sum(1 for term in normalized_terms if _contains_term(stripped.lower(), term)),
                len(candidates),
                stripped,
                local_start,
                local_start + len(stripped),
            )
        )
    relevant = [candidate for candidate in candidates if candidate[0] > 0]
    maximum_score = max((candidate[0] for candidate in relevant), default=0)
    threshold = max(1, maximum_score - 1)
    relevant = [candidate for candidate in relevant if candidate[0] >= threshold]
    selected = sorted(sorted(relevant, key=lambda item: (-item[0], item[1]))[:limit], key=lambda item: item[1])
    return tuple((sentence, local_start, local_end) for _score, _index, sentence, local_start, local_end in selected)


def _structured_requirement_fragments(
    text: str,
    query_terms: tuple[str, ...],
    limit: int = 12,
) -> tuple[tuple[str, int, int], ...]:
    """Extract evidence-addressable Markdown tables and timing-diagram rows."""

    lines = text.splitlines(keepends=True)
    offsets: list[int] = []
    offset = 0
    for line in lines:
        offsets.append(offset)
        offset += len(line)
    normalized_terms = tuple(term.lower() for term in query_terms if term)
    candidates: list[tuple[int, int, str, int, int]] = []
    index = 0
    while index + 1 < len(lines):
        header = _markdown_cells(lines[index])
        separator = _markdown_cells(lines[index + 1])
        if (
            header
            and separator
            and len(header) == len(separator)
            and all(re.fullmatch(r":?-{3,}:?", cell.replace(" ", "")) for cell in separator)
        ):
            row = index + 2
            while row < len(lines):
                cells = _markdown_cells(lines[row])
                if not cells or len(cells) != len(header):
                    break
                values = {name.lower(): value for name, value in zip(header, cells, strict=True)}
                statement = _table_requirement_statement(values)
                if statement:
                    score = sum(1 for term in normalized_terms if _contains_term(statement.lower(), term))
                    if score or any(word in statement.lower() for word in ("shall", "must", "coverage", "register")):
                        start = offsets[row] + len(lines[row]) - len(lines[row].lstrip())
                        end = offsets[row] + len(lines[row].rstrip())
                        candidates.append((max(score, 1), len(candidates), statement, start, end))
                row += 1
            index = row
            continue
        index += 1
    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped or not re.search(r"(?:--?>|<--?|=>|rising|falling|\|[_‾]+\|)", stripped, re.IGNORECASE):
            continue
        score = sum(1 for term in normalized_terms if _contains_term(stripped.lower(), term))
        if not score:
            continue
        start = offsets[line_index] + len(line) - len(line.lstrip())
        candidates.append((score, len(candidates), f"Timing diagram: {stripped}", start, start + len(stripped)))
    selected = sorted(candidates, key=lambda item: (-item[0], item[1]))[:limit]
    return tuple((statement, start, end) for _score, _order, statement, start, end in selected)


def _markdown_cells(line: str) -> tuple[str, ...]:
    stripped = line.strip()
    if "|" not in stripped:
        return ()
    return tuple(cell.strip() for cell in stripped.strip("|").split("|"))


def _table_requirement_statement(values: dict[str, str]) -> str | None:
    requirement = next(
        (values[name] for name in ("requirement", "behavior", "description", "constraint") if values.get(name)),
        None,
    )
    signal = next((values[name] for name in ("signal", "field", "channel") if values.get(name)), None)
    register = next((values[name] for name in ("register", "name") if values.get(name)), None)
    offset = values.get("offset") or values.get("address")
    access = values.get("access")
    reset = values.get("reset") or values.get("reset value")
    if register and (offset or access or reset):
        details = [f"Register {register}"]
        if offset:
            details.append(f"at offset {offset}")
        if access:
            details.append(f"has {access} access")
        if reset:
            details.append(f"resets to {reset}")
        if requirement:
            details.append(requirement)
        return "; ".join(details) + "."
    if signal and requirement:
        direction = values.get("direction")
        width = values.get("width")
        qualifiers = " ".join(item for item in (direction, width) if item)
        return f"Signal {signal}{' (' + qualifiers + ')' if qualifiers else ''}: {requirement}"
    if requirement:
        return requirement
    return None


def _walk_expressions(expressions: tuple[RTLExpression, ...]) -> tuple[RTLExpression, ...]:
    return tuple(expression for root in expressions for expression in (root, *_walk_expressions(root.children)))


def _canonical_requirement(statement: str) -> str:
    normalized = statement.lower().replace("’", "'")
    normalized = re.sub(r"\b(?:the\s+)?(?:module|design|dut)\b", " ", normalized)
    normalized = re.sub(r"\b(?:shall|must|should|will)\b", " ", normalized)
    normalized = re.sub(r"[^a-z0-9_']+", " ", normalized)
    return " ".join(normalized.split())


def _requirement_category(statement: str) -> str:
    normalized = statement.lower()
    categories = (
        ("register", ("register", "offset", "read-only", "write-one-to-clear")),
        ("performance", ("throughput", "bandwidth", "performance", "transactions/cycle", "beats/cycle")),
        ("power", ("power", "sleep", "retention", "isolation")),
        ("coverage", ("coverage", "coverpoint", "cross")),
        ("timing", ("timing diagram", "rising edge", "falling edge", "setup", "hold time")),
        ("reset", ("reset", "resets", "clear", "clears", "cleared", "active-high", "active-low")),
        ("increment", ("increment", "increments", "increase", "increases")),
        ("hold", ("hold", "holds", "stable", "unchanged")),
        ("latency", ("latency", "cycle", "cycles", "within")),
        ("error", ("error", "fault", "invalid", "overflow", "underflow")),
        ("ordering", ("order", "ordering", "before", "after")),
        ("debug", ("debug", "observe", "observable", "trace")),
        ("protocol", ("protocol", "transaction", "transfer", "handshake", "valid", "ready", "backpressure")),
        ("connectivity", ("connect", "route", "forward", "mirror", "reflect", "wrapper")),
    )
    return next((category for category, terms in categories if _mentions_any(normalized, terms)), "general")


def _requirement_expected_value(statement: str, category: str) -> str | None:
    normalized = statement.lower().replace("’", "'")
    if category == "reset":
        return _reset_expected_value(normalized)
    if category == "latency":
        match = re.search(r"(?:within|after|latency(?:\s+of)?|in)\s+(\d+)\s+cycles?", normalized)
        if match:
            return f"{match.group(1)} cycles"
    if category == "increment":
        match = re.search(r"(?:increment|increase)(?:s|ed)?(?:\s+\w+){0,2}\s+by\s+(\d+)", normalized)
        return match.group(1) if match else "1"
    if category == "hold":
        return "stable"
    if category == "performance":
        return _performance_expected_value(normalized)
    if category == "power":
        return _power_expected_value(normalized)
    if category == "coverage":
        return _coverage_expected_value(normalized)
    return None


def _reset_expected_value(normalized: str) -> str | None:
    match = re.search(
        r"(?:to|value(?:\s+of)?|becomes?)\s+(zero|one|0|1|'0|'1|\d+'[s]?[bhd][0-9a-f_xz]+)",
        normalized,
    )
    if match:
        value = match.group(1)
        return {"zero": "0", "one": "1", "'0": "0", "'1": "1"}.get(value, value)
    if "active-high" in normalized or "active high" in normalized:
        return "active_high"
    if "active-low" in normalized or "active low" in normalized:
        return "active_low"
    return None


def _performance_expected_value(normalized: str) -> str | None:
    match = re.search(
        r"(?:at\s+least|minimum|sustain(?:s|ed)?|throughput(?:\s+of)?)\s+(\d+(?:\.\d+)?)\s*"
        r"(transactions?/cycle|beats?/cycle|gb/s|mb/s|mhz|ghz)",
        normalized,
    )
    return f">={match.group(1)} {match.group(2)}" if match else None


def _power_expected_value(normalized: str) -> str | None:
    state = re.search(r"\b(retention|isolation|sleep|power[- ]?down|power[- ]?up)\b", normalized)
    cycles = re.search(r"(?:within|after)\s+(\d+)\s+cycles?", normalized)
    return state.group(1) + (f" within {cycles.group(1)} cycles" if cycles else "") if state else None


def _coverage_expected_value(normalized: str) -> str | None:
    cross = re.search(r"\bcross\s+([a-z0-9_]+)\s+(?:and|x)\s+([a-z0-9_]+)", normalized)
    percentage = re.search(r"(\d+(?:\.\d+)?)\s*%", normalized)
    if cross:
        return f"cross {cross.group(1)} x {cross.group(2)}"
    return f">={percentage.group(1)}%" if percentage else None


def _requirement_condition(module: RTLModule, statement: str) -> str | None:
    normalized = statement.lower()
    candidates = (*module.resets, *(port.name for port in module.port_details if port.direction == "input"))
    return next((name for name in dict.fromkeys(candidates) if _contains_term(normalized, name.lower())), None)


def _requirement_summary(
    text: str,
    query_terms: tuple[str, ...] = (),
    max_chars: int = 500,
) -> str:
    sentences = tuple(sentence.strip() for sentence in re.split(r"(?<=[.!?])\s+|\n\s*\n", text) if sentence.strip())
    normalized_terms = tuple(term.lower() for term in query_terms if term)
    scored = tuple(
        (index, sentence, sum(1 for term in normalized_terms if term in sentence.lower()))
        for index, sentence in enumerate(sentences)
    )
    maximum_score = max((score for _index, _sentence, score in scored), default=0)
    threshold = max(1, maximum_score - 1)
    selected_indexes = sorted(index for index, _sentence, score in scored if score >= threshold)[:3]
    summary = " ".join(sentences[index] for index in selected_indexes) if selected_indexes else " ".join(text.split())
    if len(summary) <= max_chars:
        return summary
    return summary[: max_chars - 3].rstrip() + "..."
