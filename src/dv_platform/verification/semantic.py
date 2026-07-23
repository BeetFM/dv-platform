"""Parser-neutral semantic IR. Unknown values are deliberate, not omissions."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from dv_platform.core.models import EvidenceRef

Unknown = Literal["unknown"]


@dataclass(frozen=True)
class SemanticExpression:
    operator: str
    width: int | Unknown = "unknown"
    signed: bool | Unknown = "unknown"
    cast: str | Unknown = "unknown"
    children: tuple[SemanticExpression, ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class SemanticBranch:
    condition: SemanticExpression | None
    path: str
    priority: bool | Unknown = "unknown"
    mutually_exclusive: bool | Unknown = "unknown"
    is_default: bool = False
    evidence_refs: tuple[EvidenceRef, ...] = ()


@dataclass(frozen=True)
class SemanticIR:
    module: str
    expressions: tuple[SemanticExpression, ...] = ()
    branches: tuple[SemanticBranch, ...] = ()
    generate_conditions: tuple[SemanticExpression, ...] = ()
    qualified_symbols: tuple[str, ...] = ()
    interface_directions: tuple[tuple[str, str], ...] = ()
    assertions: tuple[str, ...] = ()
    covers: tuple[str, ...] = ()
    domain_relationships: tuple[tuple[str, str, str], ...] = ()
    transaction_groups: tuple[tuple[str, tuple[str, ...]], ...] = ()
    evidence_refs: tuple[EvidenceRef, ...] = ()

    def validate(self, evidence_ids: set[str]) -> None:
        refs = (
            self.evidence_refs
            + tuple(
                ref for expression in (*self.expressions, *self.generate_conditions) for ref in expression.evidence_refs
            )
            + tuple(ref for branch in self.branches for ref in branch.evidence_refs)
        )
        unknown = {ref.locator for ref in refs if ref.locator not in evidence_ids and ref.source_id not in evidence_ids}
        if unknown:
            raise ValueError(f"semantic IR references unknown evidence: {sorted(unknown)}")


def generation_blockers(ir: SemanticIR) -> tuple[str, ...]:
    """Return deterministic reasons executable generation must remain blocked."""

    blockers: list[str] = []
    for expression in (*ir.expressions, *ir.generate_conditions):
        if expression.operator in {"unknown", "unsupported"}:
            blockers.append(f"unsupported expression operator: {expression.operator}")
        if expression.cast == "unknown" and expression.operator in {"cast", "truncate", "extend"}:
            blockers.append(f"unknown cast semantics for {expression.operator}")
    for branch in ir.branches:
        if branch.condition is None:
            blockers.append(f"missing branch condition: {branch.path}")
        if branch.mutually_exclusive == "unknown":
            blockers.append(f"unknown branch exclusivity: {branch.path}")
    return tuple(dict.fromkeys(blockers))


def executable_semantics(ir: SemanticIR, evidence_ids: set[str]) -> bool:
    """Validate evidence and report whether the IR is safe for executable generation."""

    ir.validate(evidence_ids)
    return not generation_blockers(ir)


for _name, _value in tuple(globals().items()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.agent.semantic"
