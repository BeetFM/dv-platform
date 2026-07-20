"""RTL and documentation analysis entry points.

Implementation modules are loaded only when a public export is first used.
"""

from importlib import import_module
from typing import Any

_EXPORTS = {
    name: (module, name)
    for module, names in {
        "dv_platform.analysis.claims": (
            "ClaimAction",
            "ClaimValidation",
            "GenerationGate",
            "check_ast_claim",
            "check_claim_evidence",
            "check_clock_claim",
            "check_documentation_claim",
            "check_module_ports_claim",
            "check_port_claim",
            "check_requirement_behavior_claim",
            "check_requirement_signal_refs_claim",
            "check_reset_claim",
            "claim_report_json",
            "claim_report_markdown",
            "classify_claim_validation",
            "classify_claims",
            "gate_generation",
            "write_claim_reports",
        ),
        "dv_platform.analysis.docs": (
            "LoadedDocument",
            "RetrievalResult",
            "chunk_document",
            "chunk_documents",
            "discover_documentation_files",
            "load_document",
            "load_documents",
            "read_configured_document_index",
            "read_document_index",
            "retrieve_chunks",
            "retrieve_chunks_with_vectors",
            "write_document_index",
        ),
        "dv_platform.analysis.plan_store": ("read_plan_records", "read_stored_plans", "write_plan_outputs"),
        "dv_platform.analysis.planner": ("create_initial_plan",),
        "dv_platform.analysis.review": (
            "generate_design_decisions",
            "generate_run_feedback_decisions",
            "read_review_records",
            "write_review_outputs",
        ),
        "dv_platform.analysis.rtl": (
            "normalize_verilator_xml",
            "read_normalized_rtl_facts",
            "run_verilator_xml",
            "write_normalized_rtl_facts",
        ),
    }.items()
    for name in names
}


def __getattr__(name: str) -> Any:
    try:
        module_name, export_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value


__all__ = [
    "ClaimAction",
    "ClaimValidation",
    "GenerationGate",
    "check_ast_claim",
    "check_claim_evidence",
    "check_clock_claim",
    "check_documentation_claim",
    "check_module_ports_claim",
    "check_port_claim",
    "check_requirement_behavior_claim",
    "check_requirement_signal_refs_claim",
    "check_reset_claim",
    "claim_report_json",
    "claim_report_markdown",
    "LoadedDocument",
    "RetrievalResult",
    "chunk_document",
    "chunk_documents",
    "classify_claim_validation",
    "classify_claims",
    "gate_generation",
    "write_claim_reports",
    "discover_documentation_files",
    "create_initial_plan",
    "read_plan_records",
    "read_stored_plans",
    "load_document",
    "load_documents",
    "read_configured_document_index",
    "normalize_verilator_xml",
    "read_normalized_rtl_facts",
    "run_verilator_xml",
    "write_normalized_rtl_facts",
    "read_document_index",
    "retrieve_chunks",
    "retrieve_chunks_with_vectors",
    "write_document_index",
    "write_plan_outputs",
    "generate_design_decisions",
    "generate_run_feedback_decisions",
    "read_review_records",
    "write_review_outputs",
]
