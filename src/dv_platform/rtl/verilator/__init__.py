"""Verilator-authoritative SystemVerilog and Verilog ingestion."""

from __future__ import annotations

from dv_platform.analysis.discovery import ProjectInventory
from dv_platform.core.models import CLIConfig
from dv_platform.rtl.frontend import RTLAnalysisResult


class VerilatorFrontend:
    """Run Verilator and normalize its elaborated XML into domain records."""

    frontend_id = "verilator"
    languages = ("verilog", "systemverilog")

    def analyze(self, config: CLIConfig, inventory: ProjectInventory) -> RTLAnalysisResult:
        from dv_platform.analysis.rtl import normalize_verilator_xml, run_verilator_xml

        run = run_verilator_xml(config, inventory)
        if run.return_code != 0:
            return RTLAnalysisResult(
                frontend=self.frontend_id,
                modules=(),
                diagnostics=(f"Verilator exited with status {run.return_code}",),
                artifacts=(run.stdout_log, run.stderr_log, run.version_log),
            )
        modules = normalize_verilator_xml(
            run.xml_files,
            protocol_profiles=config.protocol_profiles,
            production_protocol_bindings=config.production_protocol_bindings,
        )
        evidence = tuple(ref for module in modules for ref in module.ast_refs)
        return RTLAnalysisResult(
            frontend=self.frontend_id,
            modules=modules,
            evidence_refs=evidence,
            artifacts=(*run.xml_files, run.stdout_log, run.stderr_log, run.version_log),
        )
