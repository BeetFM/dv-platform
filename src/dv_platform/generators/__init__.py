"""Verification artifact generation backends."""

from dv_platform.generators.artifacts import ArtifactWriteResult, write_generated_artifacts
from dv_platform.generators.base import GeneratorBackend, GeneratorRegistry
from dv_platform.generators.cocotb import CocotbGenerator

__all__ = [
    "ArtifactWriteResult",
    "CocotbGenerator",
    "GeneratorBackend",
    "GeneratorRegistry",
    "write_generated_artifacts",
]
