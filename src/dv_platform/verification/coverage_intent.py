"""Typed functional coverage intent and fail-closed observation reconciliation."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass

COVERAGE_INTENT_FORMAT_VERSION = 1
NON_CLOSING_STATES = frozenset(
    {
        "missing",
        "stale",
        "orphaned",
        "excluded_only",
        "intentionally_missed",
        "zero_denominator",
        "uncovered",
    }
)
_SPACE = re.compile(r"\s+")


def _normalized_name(value: str) -> str:
    normalized = _SPACE.sub(" ", value.strip()).lower()
    if not normalized:
        raise ValueError("coverage intent name must not be empty")
    return normalized


def canonical_coverage_intent_id(
    *,
    source_locator: str,
    hierarchy: str,
    specialization: str,
    kind: str,
    name: str,
    members: tuple[str, ...] = (),
    format_version: int = COVERAGE_INTENT_FORMAT_VERSION,
) -> str:
    """Return the canonical SHA-256 identity for one bin or cross."""

    if kind not in {"bin", "cross"}:
        raise ValueError("coverage intent kind must be bin or cross")
    if not source_locator or not hierarchy or not specialization:
        raise ValueError("coverage intent requires source locator, hierarchy, and specialization")
    normalized_members = tuple(sorted(set(members)))
    if kind == "bin" and normalized_members:
        raise ValueError("coverage bins cannot contain cross members")
    if kind == "cross" and len(normalized_members) < 2:
        raise ValueError("coverage crosses require at least two distinct canonical bin IDs")
    payload = {
        "format_version": format_version,
        "source_locator": source_locator,
        "hierarchy": hierarchy,
        "specialization": specialization,
        "kind": kind,
        "normalized_name": _normalized_name(name),
        "members": normalized_members,
    }
    digest = hashlib.sha256(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")).hexdigest()
    return f"covintent-v{format_version}-{digest}"


@dataclass(frozen=True)
class CoverageIntent:
    source_locator: str
    hierarchy: str
    specialization: str
    kind: str
    name: str
    revision: str
    members: tuple[str, ...] = ()
    intentionally_missed: bool = False

    def __post_init__(self) -> None:
        if not self.revision:
            raise ValueError("coverage intent revision must not be empty")
        canonical_coverage_intent_id(
            source_locator=self.source_locator,
            hierarchy=self.hierarchy,
            specialization=self.specialization,
            kind=self.kind,
            name=self.name,
            members=self.members,
        )

    @property
    def point_id(self) -> str:
        return canonical_coverage_intent_id(
            source_locator=self.source_locator,
            hierarchy=self.hierarchy,
            specialization=self.specialization,
            kind=self.kind,
            name=self.name,
            members=self.members,
        )


@dataclass(frozen=True)
class CoverageObservation:
    point_id: str
    revision: str
    hits: int
    denominator: int = 1
    excluded: bool = False

    def __post_init__(self) -> None:
        if not self.point_id or not self.revision:
            raise ValueError("coverage observation requires point ID and revision")
        if self.hits < 0 or self.denominator < 0:
            raise ValueError("coverage observation hits and denominator must be non-negative")


def reconcile_coverage_intent(
    intents: tuple[CoverageIntent, ...],
    observations: tuple[CoverageObservation, ...],
) -> tuple[dict[str, object], ...]:
    """Reconcile canonical intent and observations without allowing ambiguous closure."""

    intent_by_id = _unique_by_id(((intent.point_id, intent) for intent in intents), "intent")
    observations_by_id: dict[str, list[CoverageObservation]] = {}
    for observation in observations:
        observations_by_id.setdefault(observation.point_id, []).append(observation)
    records: list[dict[str, object]] = []
    for point_id, intent in sorted(intent_by_id.items()):
        matching = observations_by_id.pop(point_id, ())
        status = _intent_status(intent, tuple(matching))
        records.append(
            {
                "point_id": point_id,
                "kind": intent.kind,
                "name": _normalized_name(intent.name),
                "members": tuple(sorted(set(intent.members))),
                "status": status,
                "closing": status == "covered",
            }
        )
    for point_id, orphaned in sorted(observations_by_id.items()):
        records.append(
            {
                "point_id": point_id,
                "kind": "unknown",
                "name": "",
                "members": (),
                "status": "orphaned",
                "closing": False,
                "observations": len(orphaned),
            }
        )
    return tuple(records)


def _unique_by_id(items, label):
    result = {}
    for point_id, value in items:
        if point_id in result:
            raise ValueError(f"duplicate canonical coverage {label} ID: {point_id}")
        result[point_id] = value
    return result


def _intent_status(intent: CoverageIntent, observations: tuple[CoverageObservation, ...]) -> str:
    if not observations:
        return "missing"
    if any(observation.revision != intent.revision for observation in observations):
        return "stale"
    if all(observation.excluded for observation in observations):
        return "excluded_only"
    if intent.intentionally_missed:
        return "intentionally_missed"
    included = tuple(observation for observation in observations if not observation.excluded)
    if not included or sum(observation.denominator for observation in included) == 0:
        return "zero_denominator"
    return "covered" if sum(observation.hits for observation in included) > 0 else "uncovered"
