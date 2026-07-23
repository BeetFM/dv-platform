"""Deterministic traceability graph for targeted regeneration and rerun closure."""

from __future__ import annotations

from dataclasses import dataclass

from dv_platform.core.models import GeneratedArtifact, VerificationPlan


@dataclass(frozen=True)
class DependencySelection:
    document_ids: tuple[str, ...]
    fact_ids: tuple[str, ...]
    check_ids: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    generated_symbols: tuple[str, ...]
    artifact_paths: tuple[str, ...]
    run_targets: tuple[str, ...]
    coverage_point_ids: tuple[str, ...]
    review_ids: tuple[str, ...]


@dataclass(frozen=True)
class VerificationDependencyGraph:
    """A stable directed graph from plan intent through executable evidence."""

    edges: tuple[tuple[str, str], ...]

    def affected(self, seeds: tuple[str, ...]) -> DependencySelection:
        pending = [_node(value) for value in seeds]
        reached = set(pending)
        adjacency: dict[str, list[str]] = {}
        for source, destination in self.edges:
            adjacency.setdefault(source, []).append(destination)
        while pending:
            source = pending.pop()
            for destination in adjacency.get(source, ()):
                if destination in reached:
                    continue
                reached.add(destination)
                pending.append(destination)
        return DependencySelection(
            check_ids=_values(reached, "check"),
            document_ids=_values(reached, "document"),
            fact_ids=_values(reached, "fact"),
            scenario_ids=_values(reached, "scenario"),
            generated_symbols=_values(reached, "symbol"),
            artifact_paths=_values(reached, "artifact"),
            run_targets=_values(reached, "run"),
            coverage_point_ids=_values(reached, "coverage"),
            review_ids=_values(reached, "review"),
        )


def build_dependency_graph(
    plan: VerificationPlan,
    artifacts: tuple[GeneratedArtifact, ...] = (),
    reviews: tuple[str, ...] = (),
) -> VerificationDependencyGraph:
    edges: set[tuple[str, str]] = set()
    scenarios_by_check, scenarios_by_requirement = _scenario_edges(plan, edges)
    _check_edges(plan, edges)
    _artifact_edges(artifacts, scenarios_by_check, scenarios_by_requirement, edges)
    _requirement_edges(plan, edges)
    run_nodes = {destination for _source, destination in edges if destination.startswith("run:")}
    coverage_nodes = {destination for _source, destination in edges if destination.startswith("coverage:")}
    for review in reviews:
        review_node = _typed("review", review)
        for source in (*sorted(run_nodes), *sorted(coverage_nodes)):
            edges.add((source, review_node))
    return VerificationDependencyGraph(tuple(sorted(edges)))


def _scenario_edges(
    plan: VerificationPlan,
    edges: set[tuple[str, str]],
) -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    scenarios_by_check: dict[str, set[str]] = {}
    scenarios_by_requirement: dict[str, set[str]] = {}
    for scenario in plan.scenarios:
        scenario_node = _typed("scenario", scenario.scenario_id)
        for check_id in scenario.check_ids:
            edges.add((_typed("check", check_id), scenario_node))
            scenarios_by_check.setdefault(check_id, set()).add(scenario.scenario_id)
        for requirement_id in scenario.requirement_ids:
            edges.add((_typed("requirement", requirement_id), scenario_node))
            scenarios_by_requirement.setdefault(requirement_id, set()).add(scenario.scenario_id)
        for requirement_id in scenario.requirement_ids:
            for check_id in scenario.check_ids:
                edges.add((_typed("requirement", requirement_id), _typed("check", check_id)))
        for goal in scenario.coverage_goals:
            edges.add((scenario_node, _typed("coverage", goal.goal_id)))
    return scenarios_by_check, scenarios_by_requirement


def _check_edges(plan: VerificationPlan, edges: set[tuple[str, str]]) -> None:
    for check in plan.check_details:
        for ref in check.evidence_refs:
            kind = "document" if ref.kind.value == "document_chunk" else "fact"
            edges.add((_typed(kind, f"{ref.source_id}:{ref.locator}"), _typed("check", check.check_id)))
        for point_id in check.coverage_point_ids:
            edges.add((_typed("check", check.check_id), _typed("coverage", point_id)))


def _artifact_edges(
    artifacts: tuple[GeneratedArtifact, ...],
    scenarios_by_check: dict[str, set[str]],
    scenarios_by_requirement: dict[str, set[str]],
    edges: set[tuple[str, str]],
) -> None:
    for artifact in artifacts:
        artifact_id = f"{artifact.target.value}/{artifact.source_plan_module}/{artifact.path.as_posix()}"
        artifact_node = _typed("artifact", artifact_id)
        run_id = f"{artifact.target.value}/{artifact.source_plan_module}"
        edges.add((artifact_node, _typed("run", run_id)))
        edges.add((_typed("run", run_id), _typed("coverage", run_id)))
        for trace in artifact.traceability:
            symbol_id = f"{artifact.target.value}/{artifact.source_plan_module}/{trace.generated_symbol}"
            symbol_node = _typed("symbol", symbol_id)
            edges.add((symbol_node, artifact_node))
            for check_id in trace.check_ids:
                edges.add((_typed("check", check_id), symbol_node))
                for scenario_id in scenarios_by_check.get(check_id, ()):
                    edges.add((_typed("scenario", scenario_id), symbol_node))
            for requirement_id in trace.requirement_ids:
                edges.add((_typed("requirement", requirement_id), symbol_node))
                for scenario_id in scenarios_by_requirement.get(requirement_id, ()):
                    edges.add((_typed("scenario", scenario_id), symbol_node))


def _requirement_edges(plan: VerificationPlan, edges: set[tuple[str, str]]) -> None:
    for requirement in plan.structured_requirements:
        for ref in requirement.evidence_refs:
            kind = "document" if ref.kind.value == "document_chunk" else "fact"
            edges.add(
                (_typed(kind, f"{ref.source_id}:{ref.locator}"), _typed("requirement", requirement.requirement_id))
            )


def _node(value: str) -> str:
    return value if ":" in value and value.split(":", 1)[0] in _KINDS else _typed("check", value)


def _typed(kind: str, value: str) -> str:
    return f"{kind}:{value}"


def _values(nodes: set[str], kind: str) -> tuple[str, ...]:
    prefix = f"{kind}:"
    return tuple(sorted(node.removeprefix(prefix) for node in nodes if node.startswith(prefix)))


_KINDS = {"document", "fact", "requirement", "check", "scenario", "symbol", "artifact", "run", "coverage", "review"}

for _legacy_class in (DependencySelection, VerificationDependencyGraph):
    _legacy_class.__module__ = "dv_platform.analysis.dependencies"
del _legacy_class
