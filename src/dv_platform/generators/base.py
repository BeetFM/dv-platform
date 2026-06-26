"""Interfaces for language-specific verification generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from importlib import metadata
from typing import Protocol

from dv_platform.core.models import GeneratedArtifact, VerificationPlan, VerificationTarget


GENERATOR_PLUGIN_ENTRY_POINT_GROUP = "dv_platform.generators"


class GeneratorBackend(Protocol):
    """Protocol implemented by each code generation backend."""

    target: VerificationTarget

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        """Generate artifacts for a verification plan."""


@dataclass
class GeneratorRegistry:
    """Registry for selecting backends by verification target."""

    _backends: dict[VerificationTarget, GeneratorBackend] = field(default_factory=dict)

    def register(self, backend: GeneratorBackend) -> None:
        self._backends[backend.target] = backend

    def get(self, target: VerificationTarget) -> GeneratorBackend:
        try:
            return self._backends[target]
        except KeyError as exc:
            raise LookupError(f"No generator registered for target: {target}") from exc

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        artifacts: list[GeneratedArtifact] = []
        for target in plan.targets:
            artifacts.extend(self.get(target).generate(plan))
        return artifacts


def load_generator_plugins(
    registry: GeneratorRegistry,
    enabled_plugins: tuple[str, ...],
    entry_points: object | None = None,
) -> tuple[str, ...]:
    """Load explicitly enabled generator backend plugins from package entry points."""

    if not enabled_plugins:
        return ()

    discovered = _generator_entry_points(entry_points)
    loaded: list[str] = []
    for plugin_name in enabled_plugins:
        entry_point = discovered.get(plugin_name)
        if entry_point is None:
            raise LookupError(f"Enabled generator plugin was not found: {plugin_name}")
        backend = _backend_from_entry_point(entry_point)
        registry.register(backend)
        loaded.append(plugin_name)
    return tuple(loaded)


def _generator_entry_points(entry_points: object | None) -> dict[str, object]:
    discovered = metadata.entry_points() if entry_points is None else entry_points
    if hasattr(discovered, "select"):
        selected = discovered.select(group=GENERATOR_PLUGIN_ENTRY_POINT_GROUP)
    elif isinstance(discovered, dict):
        selected = discovered.get(GENERATOR_PLUGIN_ENTRY_POINT_GROUP, ())
    else:
        selected = discovered
    return {str(entry_point.name): entry_point for entry_point in selected}


def _backend_from_entry_point(entry_point: object) -> GeneratorBackend:
    loaded = entry_point.load()
    if isinstance(loaded, type):
        backend = loaded()
        if hasattr(backend, "target") and hasattr(backend, "generate"):
            return backend
    if hasattr(loaded, "target") and hasattr(loaded, "generate"):
        return loaded
    if callable(loaded):
        backend = loaded()
        if hasattr(backend, "target") and hasattr(backend, "generate"):
            return backend
    raise TypeError(f"Generator plugin does not provide a backend: {getattr(entry_point, 'name', entry_point)}")
