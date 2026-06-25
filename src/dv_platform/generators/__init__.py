"""Verification artifact generation backends."""

from dv_platform.generators.artifacts import ArtifactWriteResult, write_generated_artifacts
from dv_platform.generators.base import GeneratorBackend, GeneratorRegistry
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.formal import FormalGenerator

__all__ = [
    "ArtifactWriteResult",
    "CocotbGenerator",
    "FormalGenerator",
    "GeneratorBackend",
    "GeneratorRegistry",
    "write_generated_artifacts",
]
