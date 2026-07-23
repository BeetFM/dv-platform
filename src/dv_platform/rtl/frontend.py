"""Common contracts for authoritative HDL frontends."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from dv_platform.core.models import EvidenceRef, RTLModule


@dataclass(frozen=True)
class RTLAnalysisResult:
    """Normalized, provenance-bearing result returned by every HDL frontend."""

    frontend: str
    modules: tuple[RTLModule, ...]
    evidence_refs: tuple[EvidenceRef, ...] = ()
    diagnostics: tuple[str, ...] = ()
    artifacts: tuple[Path, ...] = ()
    authoritative: bool = True


class HDLFrontend(Protocol):
    """Language frontend that produces the platform's normalized RTL facts."""

    frontend_id: str
    languages: tuple[str, ...]

    def analyze(self, *args: object, **kwargs: object) -> RTLAnalysisResult:
        """Analyze configured HDL input and return normalized facts."""
