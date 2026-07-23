# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Optional, evidence-bounded AI augmentation for deterministic plans."""

from __future__ import annotations

import json
import re
from typing import Any

AGENT_VERSION = "litellm-gateway-v2"
PROMPT_VERSION = "planning-proposal-v2"
PROPOSAL_SCHEMA_VERSION = 2
RUN_RECORD_SCHEMA_VERSION = 2
CACHE_SCHEMA_VERSION = 1
MAX_PROPOSAL_ITEMS = 100
MAX_STATEMENT_CHARS = 4096
MAX_SMALL_VALUE_CHARS = 512
SOURCE_CONTEXT_RADIUS = 3
MAX_SOURCE_SNIPPETS = 24
MAX_SOURCE_SNIPPET_LINES = 12


def proposal_json_schema() -> dict[str, Any]:
    """Return the strict provider-facing PlanningProposal JSON schema."""

    evidence_ids = {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True}
    note = {
        "type": "object",
        "additionalProperties": False,
        "required": ["statement", "evidence_ids"],
        "properties": {"statement": {"type": "string"}, "evidence_ids": evidence_ids},
    }
    return {
        "type": "object",
        "additionalProperties": False,
        "required": [
            "schema_version",
            "module",
            "requirements",
            "checks",
            "scenarios",
            "assumptions",
            "open_questions",
        ],
        "properties": {
            "schema_version": {"type": "integer", "const": PROPOSAL_SCHEMA_VERSION},
            "module": {"type": "string"},
            "requirements": {
                "type": "array",
                "maxItems": MAX_PROPOSAL_ITEMS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": [
                        "proposal_id",
                        "statement",
                        "signals",
                        "condition",
                        "expected_value",
                        "evidence_ids",
                    ],
                    "properties": {
                        "proposal_id": {"type": "string"},
                        "statement": {"type": "string"},
                        "signals": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        "condition": {"type": ["string", "null"]},
                        "expected_value": {"type": ["string", "null"]},
                        "evidence_ids": evidence_ids,
                    },
                },
            },
            "checks": {
                "type": "array",
                "maxItems": MAX_PROPOSAL_ITEMS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["proposal_id", "statement", "requirement_ids", "evidence_ids"],
                    "properties": {
                        "proposal_id": {"type": "string"},
                        "statement": {"type": "string"},
                        "requirement_ids": {
                            "type": "array",
                            "items": {"type": "string"},
                            "minItems": 1,
                            "uniqueItems": True,
                        },
                        "evidence_ids": evidence_ids,
                    },
                },
            },
            "scenarios": {
                "type": "array",
                "maxItems": MAX_PROPOSAL_ITEMS,
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["proposal_id", "kind", "requirement_ids", "check_ids", "evidence_ids", "parameters"],
                    "properties": {
                        "proposal_id": {"type": "string"},
                        "kind": {
                            "type": "string",
                            "enum": [
                                "apb4_transfer",
                                "apb4_register_access",
                                "axi4_lite_single_outstanding",
                                "reset_sequence",
                            ],
                        },
                        "requirement_ids": {"type": "array", "items": {"type": "string"}, "uniqueItems": True},
                        "check_ids": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
                        "evidence_ids": evidence_ids,
                        "parameters": {
                            "type": "object",
                            "additionalProperties": {"type": ["string", "integer", "boolean"]},
                        },
                    },
                },
            },
            "assumptions": {"type": "array", "maxItems": MAX_PROPOSAL_ITEMS, "items": note},
            "open_questions": {"type": "array", "maxItems": MAX_PROPOSAL_ITEMS, "items": note},
        },
    }


def validate_proposal(
    raw: str | bytes | dict[str, Any],
    *,
    module: str,
    evidence_ids: frozenset[str] | set[str],
    known_signals: frozenset[str] | set[str],
    max_chars: int = 524_288,
) -> PlanningProposal:
    """Parse and strictly validate a complete module proposal."""

    data = _proposal_document(raw, max_chars)
    root, proposal_module = _proposal_root(data, module)
    requirements, checks, scenarios = _proposal_items(root, evidence_ids, known_signals)
    assumptions = tuple(
        _parse_note(item, f"assumptions[{index}]", evidence_ids)
        for index, item in enumerate(_bounded_list(root["assumptions"], "assumptions"), start=1)
    )
    questions = tuple(
        _parse_note(item, f"open_questions[{index}]", evidence_ids)
        for index, item in enumerate(_bounded_list(root["open_questions"], "open_questions"), start=1)
    )
    return PlanningProposal(
        schema_version=PROPOSAL_SCHEMA_VERSION,
        module=proposal_module,
        requirements=requirements,
        checks=checks,
        scenarios=scenarios,
        assumptions=assumptions,
        open_questions=questions,
    )


def _proposal_document(raw: str | bytes | dict[str, Any], max_chars: int) -> object:
    if isinstance(raw, bytes):
        if len(raw) > max_chars:
            raise AIPlanningError("invalid_response", "Planning proposal exceeds the configured size limit.")
        try:
            data = _strict_json_loads(raw.decode("utf-8"))
        except (UnicodeDecodeError, ValueError) as error:
            raise AIPlanningError("invalid_response", "Planning proposal is not valid JSON.") from error
    elif isinstance(raw, str):
        if len(raw) > max_chars:
            raise AIPlanningError("invalid_response", "Planning proposal exceeds the configured size limit.")
        try:
            data = _strict_json_loads(raw)
        except ValueError as error:
            raise AIPlanningError("invalid_response", "Planning proposal is not valid JSON.") from error
    else:
        data = raw
        if len(_canonical_json(data)) > max_chars:
            raise AIPlanningError("invalid_response", "Planning proposal exceeds the configured size limit.")
    return data


def _proposal_root(data: object, module: str) -> tuple[dict[str, Any], str]:
    root = _object(data, "proposal")
    version = root.get("schema_version")
    if type(version) is not int or version not in {1, PROPOSAL_SCHEMA_VERSION}:
        raise AIPlanningError("invalid_response", "Unsupported planning proposal schema_version.")
    known_fields = {"schema_version", "module", "requirements", "checks", "assumptions", "open_questions"}
    if version >= 2:
        known_fields.add("scenarios")
    _known_fields(
        root,
        known_fields,
        "proposal",
    )
    required_fields = {"schema_version", "module", "requirements", "checks", "assumptions", "open_questions"}
    if version >= 2:
        required_fields.add("scenarios")
    _required_fields(
        root,
        required_fields,
        "proposal",
    )
    proposal_module = _bounded_string(root["module"], "proposal.module", 256)
    if proposal_module != module:
        raise AIPlanningError("invalid_response", "Planning proposal module identity does not match the request.")
    return root, proposal_module


def _proposal_items(
    root: dict[str, Any],
    evidence_ids: frozenset[str] | set[str],
    known_signals: frozenset[str] | set[str],
) -> tuple[tuple[ProposalRequirement, ...], tuple[ProposalCheck, ...], tuple[ProposalScenario, ...]]:
    requirements = tuple(
        _parse_requirement(item, index, evidence_ids, known_signals)
        for index, item in enumerate(_bounded_list(root["requirements"], "requirements"), start=1)
    )
    requirement_ids = {item.proposal_id for item in requirements}
    checks = tuple(
        _parse_check(item, index, evidence_ids, requirement_ids)
        for index, item in enumerate(_bounded_list(root["checks"], "checks"), start=1)
    )
    check_ids = {item.proposal_id for item in checks}
    scenarios = tuple(
        _parse_scenario(item, index, evidence_ids, requirement_ids, check_ids)
        for index, item in enumerate(_bounded_list(root.get("scenarios", []), "scenarios"), start=1)
    )
    proposal_ids = (
        [item.proposal_id for item in requirements]
        + [item.proposal_id for item in checks]
        + [item.proposal_id for item in scenarios]
    )
    if len(proposal_ids) != len(set(proposal_ids)):
        raise AIPlanningError("invalid_response", "Planning proposal contains duplicate proposal IDs.")
    return requirements, checks, scenarios


def _parse_requirement(
    value: object,
    index: int,
    evidence_ids: frozenset[str] | set[str],
    known_signals: frozenset[str] | set[str],
) -> ProposalRequirement:
    path = f"requirements[{index}]"
    data = _object(value, path)
    fields = {"proposal_id", "statement", "signals", "condition", "expected_value", "evidence_ids"}
    _known_fields(data, fields, path)
    _required_fields(data, fields, path)
    signals = _unique_strings(data["signals"], f"{path}.signals", 64, 256, allow_empty=True)
    unknown_signals = tuple(signal for signal in signals if signal not in known_signals)
    if unknown_signals:
        raise AIPlanningError("invalid_response", f"{path} references unknown signals: {', '.join(unknown_signals)}.")
    return ProposalRequirement(
        proposal_id=_proposal_id(data["proposal_id"], f"{path}.proposal_id"),
        statement=_bounded_string(data["statement"], f"{path}.statement", MAX_STATEMENT_CHARS),
        signals=signals,
        condition=_optional_bounded_string(data["condition"], f"{path}.condition"),
        expected_value=_optional_bounded_string(data["expected_value"], f"{path}.expected_value"),
        evidence_ids=_validated_evidence_ids(data["evidence_ids"], f"{path}.evidence_ids", evidence_ids),
    )


def _parse_check(
    value: object,
    index: int,
    evidence_ids: frozenset[str] | set[str],
    requirement_ids: set[str],
) -> ProposalCheck:
    path = f"checks[{index}]"
    data = _object(value, path)
    fields = {"proposal_id", "statement", "requirement_ids", "evidence_ids"}
    _known_fields(data, fields, path)
    _required_fields(data, fields, path)
    linked = _unique_strings(data["requirement_ids"], f"{path}.requirement_ids", 64, 128)
    unknown = tuple(identifier for identifier in linked if identifier not in requirement_ids)
    if unknown:
        raise AIPlanningError(
            "invalid_response", f"{path} references unknown proposal requirements: {', '.join(unknown)}."
        )
    return ProposalCheck(
        proposal_id=_proposal_id(data["proposal_id"], f"{path}.proposal_id"),
        statement=_bounded_string(data["statement"], f"{path}.statement", MAX_STATEMENT_CHARS),
        requirement_ids=linked,
        evidence_ids=_validated_evidence_ids(data["evidence_ids"], f"{path}.evidence_ids", evidence_ids),
    )


def _parse_scenario(
    value: object,
    index: int,
    evidence_ids: frozenset[str] | set[str],
    requirement_ids: set[str],
    check_ids: set[str],
) -> ProposalScenario:
    path = f"scenarios[{index}]"
    data = _object(value, path)
    fields = {"proposal_id", "kind", "requirement_ids", "check_ids", "evidence_ids", "parameters"}
    _known_fields(data, fields, path)
    _required_fields(data, fields, path)
    kind = _bounded_string(data["kind"], f"{path}.kind", 128)
    allowed_kinds = {
        "apb4_transfer",
        "apb4_register_access",
        "axi4_lite_single_outstanding",
        "reset_sequence",
    }
    if kind not in allowed_kinds:
        raise AIPlanningError("invalid_response", f"{path} proposes an unsupported scenario kind.")
    linked_requirements = _unique_strings(data["requirement_ids"], f"{path}.requirement_ids", 64, 128, allow_empty=True)
    linked_checks = _unique_strings(data["check_ids"], f"{path}.check_ids", 64, 128)
    unknown_requirements = tuple(item for item in linked_requirements if item not in requirement_ids)
    unknown_checks = tuple(item for item in linked_checks if item not in check_ids)
    if unknown_requirements or unknown_checks:
        raise AIPlanningError("invalid_response", f"{path} contains invented requirement or check links.")
    raw_parameters = _object(data["parameters"], f"{path}.parameters")
    if len(raw_parameters) > 32:
        raise AIPlanningError("invalid_response", f"{path}.parameters exceeds the item limit.")
    parameters = tuple(
        sorted(
            (
                _bounded_string(key, f"{path}.parameters key", 128),
                _bounded_string(str(item), f"{path}.parameters.{key}", MAX_SMALL_VALUE_CHARS),
            )
            for key, item in raw_parameters.items()
            if isinstance(item, (str, int, bool))
        )
    )
    if len(parameters) != len(raw_parameters):
        raise AIPlanningError("invalid_response", f"{path}.parameters contains an unsupported value type.")
    return ProposalScenario(
        proposal_id=_proposal_id(data["proposal_id"], f"{path}.proposal_id"),
        kind=kind,
        requirement_ids=linked_requirements,
        check_ids=linked_checks,
        evidence_ids=_validated_evidence_ids(data["evidence_ids"], f"{path}.evidence_ids", evidence_ids),
        parameters=parameters,
    )


def _parse_note(value: object, path: str, evidence_ids: frozenset[str] | set[str]) -> ProposalNote:
    data = _object(value, path)
    fields = {"statement", "evidence_ids"}
    _known_fields(data, fields, path)
    _required_fields(data, fields, path)
    return ProposalNote(
        statement=_bounded_string(data["statement"], f"{path}.statement", MAX_STATEMENT_CHARS),
        evidence_ids=_validated_evidence_ids(data["evidence_ids"], f"{path}.evidence_ids", evidence_ids),
    )


def _bounded_list(value: object, path: str) -> list[object]:
    if not isinstance(value, list):
        raise AIPlanningError("invalid_response", f"{path} must be an array.")
    if len(value) > MAX_PROPOSAL_ITEMS:
        raise AIPlanningError("invalid_response", f"{path} exceeds the item limit.")
    return value


def _object(value: object, path: str) -> dict[str, Any]:
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise AIPlanningError("invalid_response", f"{path} must be an object.")
    return value


def _known_fields(data: dict[str, Any], fields: set[str], path: str) -> None:
    unknown = sorted(set(data) - fields)
    if unknown:
        raise AIPlanningError("invalid_response", f"{path} contains unknown fields: {', '.join(unknown)}.")


def _required_fields(data: dict[str, Any], fields: set[str], path: str) -> None:
    missing = sorted(fields - set(data))
    if missing:
        raise AIPlanningError("invalid_response", f"{path} is missing fields: {', '.join(missing)}.")


def _bounded_string(value: object, path: str, maximum: int) -> str:
    if not isinstance(value, str) or not value.strip() or value != value.strip():
        raise AIPlanningError("invalid_response", f"{path} must be a non-empty trimmed string.")
    if len(value) > maximum or any(ord(character) < 32 and character not in "\n\t" for character in value):
        raise AIPlanningError("invalid_response", f"{path} exceeds its string limit or contains control characters.")
    return value


def _optional_bounded_string(value: object, path: str) -> str | None:
    if value is None:
        return None
    return _bounded_string(value, path, MAX_SMALL_VALUE_CHARS)


def _proposal_id(value: object, path: str) -> str:
    identifier = _bounded_string(value, path, 128)
    if re.fullmatch(r"[A-Za-z][A-Za-z0-9_.:-]*", identifier) is None:
        raise AIPlanningError("invalid_response", f"{path} is not a valid local proposal ID.")
    return identifier


def _unique_strings(
    value: object,
    path: str,
    max_items: int,
    max_chars: int,
    allow_empty: bool = False,
) -> tuple[str, ...]:
    if not isinstance(value, list) or len(value) > max_items or (not allow_empty and not value):
        raise AIPlanningError("invalid_response", f"{path} must be a bounded non-empty array.")
    values = tuple(_bounded_string(item, path, max_chars) for item in value)
    if len(values) != len(set(values)):
        raise AIPlanningError("invalid_response", f"{path} contains duplicate values.")
    return values


def _validated_evidence_ids(
    value: object,
    path: str,
    available: frozenset[str] | set[str],
) -> tuple[str, ...]:
    identifiers = _unique_strings(value, path, 64, 64)
    unknown = tuple(identifier for identifier in identifiers if identifier not in available)
    if unknown:
        raise AIPlanningError("invalid_response", f"{path} contains unknown evidence IDs: {', '.join(unknown)}.")
    return identifiers


def _strict_json_loads(value: str) -> object:
    def object_from_pairs(pairs: list[tuple[str, object]]) -> dict[str, object]:
        result: dict[str, object] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError(f"Duplicate JSON field: {key}")
            result[key] = item
        return result

    def reject_constant(constant: str) -> object:
        raise ValueError(f"Invalid JSON constant: {constant}")

    return json.loads(value, object_pairs_hook=object_from_pairs, parse_constant=reject_constant)
