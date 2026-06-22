"""Interfaces for language-specific verification generators."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from dv_platform.core.models import GeneratedArtifact, VerificationPlan, VerificationTarget


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
