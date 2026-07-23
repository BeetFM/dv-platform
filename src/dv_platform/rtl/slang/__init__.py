"""Independent Slang semantic cross-check frontend."""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from dv_platform.rtl.frontend import RTLAnalysisResult

if TYPE_CHECKING:
    from dv_platform.analysis.semantic_crosscheck import SlangAnalyzer


class SlangFrontend:
    """Normalize Slang AST output without promoting it over Verilator."""

    frontend_id = "slang"
    languages = ("verilog", "systemverilog")

    def __init__(self, analyzer: SlangAnalyzer | None = None) -> None:
        if analyzer is None:
            from dv_platform.analysis.semantic_crosscheck import SlangAnalyzer

            analyzer = SlangAnalyzer()
        self._analyzer = analyzer

    def analyze(
        self,
        files: tuple[Path, ...],
        output_path: Path,
        *,
        top_modules: tuple[str, ...] = (),
        include_paths: tuple[Path, ...] = (),
        defines: tuple[str, ...] = (),
        parameter_overrides: tuple[str, ...] = (),
    ) -> RTLAnalysisResult:
        run = self._analyzer.run(
            files,
            output_path,
            top_modules=top_modules,
            include_paths=include_paths,
            defines=defines,
            parameter_overrides=parameter_overrides,
        )
        artifacts = (
            run.ast_path,
            run.stdout_log,
            run.stderr_log,
            run.version_log,
            run.command_log,
            run.diagnostics_path,
        )
        if not run.succeeded:
            return RTLAnalysisResult(
                frontend=self.frontend_id,
                modules=(),
                diagnostics=(run.error or "Slang did not produce semantic facts",),
                artifacts=artifacts,
                authoritative=False,
            )
        evidence = tuple(ref for module in run.modules for ref in module.ast_refs)
        return RTLAnalysisResult(
            frontend=self.frontend_id,
            modules=run.modules,
            evidence_refs=evidence,
            artifacts=artifacts,
            authoritative=False,
        )
