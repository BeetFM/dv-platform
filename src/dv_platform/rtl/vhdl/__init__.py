"""GHDL-authoritative VHDL ingestion."""

from __future__ import annotations

from pathlib import Path

from dv_platform.analysis.vhdl import normalize_vhdl_sources, validate_vhdl_elaboration
from dv_platform.core.models import ProductionProtocolBinding
from dv_platform.rtl.frontend import RTLAnalysisResult


class VHDLFrontend:
    """Normalize the supported VHDL profile and validate it with GHDL."""

    frontend_id = "ghdl-vhdl"
    languages = ("vhdl",)

    def analyze(
        self,
        source_files: tuple[Path, ...],
        *,
        work_dir: Path,
        parameter_overrides: tuple[str, ...] = (),
        top_modules: tuple[str, ...] = (),
        identity_suffix: str | None = None,
        production_protocol_bindings: tuple[ProductionProtocolBinding, ...] = (),
        architecture_bindings: tuple[tuple[str, str], ...] = (),
        executable: str = "ghdl",
    ) -> RTLAnalysisResult:
        modules = normalize_vhdl_sources(
            source_files,
            parameter_overrides=parameter_overrides,
            top_modules=top_modules,
            identity_suffix=identity_suffix,
            production_protocol_bindings=production_protocol_bindings,
            architecture_bindings=architecture_bindings,
        )
        version = validate_vhdl_elaboration(
            source_files,
            tuple(module.name for module in modules),
            work_dir,
            executable,
        )
        evidence = tuple(ref for module in modules for ref in module.ast_refs)
        return RTLAnalysisResult(
            frontend=self.frontend_id,
            modules=modules,
            evidence_refs=evidence,
            diagnostics=(version,),
        )
