"""Capture and compare deterministic dv-platform compatibility fingerprints."""

from __future__ import annotations

import argparse
import dataclasses
import hashlib
import importlib
import inspect
import json
import pkgutil
import re
import subprocess
import sys
import tomllib
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = ROOT / "src" / "dv_platform"
DEFAULT_BASELINE = ROOT / "docs" / "compatibility-baseline.json"
COMPATIBILITY_ROOTS = {
    "dv_platform.agent",
    "dv_platform.analysis",
    "dv_platform.cli",
    "dv_platform.core",
    "dv_platform.enterprise",
    "dv_platform.generators",
    "dv_platform.run",
}
INTERNAL_IMPLEMENTATION_PREFIXES = (
    "dv_platform.enterprise.qualification_",
    "dv_platform.enterprise.semantic_",
    "dv_platform.generators.artifact_",
    "dv_platform.generators.cocotb_support",
    "dv_platform.generators.protocol_",
    "dv_platform.generators.uvm_",
)
ADDITIVE_INTERNAL_SYMBOLS = {
    "dv_platform.analysis.discovery": {
        "_consume_filelist_token",
        "_extend_nested_filelist",
    },
    "dv_platform.analysis.ai_scenarios": {
        "_scenario_templates",
        "_selection_schema",
        "_selection_validator",
    },
    "dv_platform.analysis.dependencies": {
        "_artifact_edges",
        "_check_edges",
        "_requirement_edges",
        "_scenario_edges",
    },
    "dv_platform.analysis.closure": {
        "_append_coverage_questions",
    },
    "dv_platform.analysis.protocols": {
        "_profile_binding_matches",
        "_profile_channels",
        "_profile_role",
    },
    "dv_platform.analysis.revisions": {
        "_apply_proposals",
        "_revision_base",
        "_revision_identifier",
        "_revision_impact",
        "_validated_proposals",
        "_validated_scenario_selections",
    },
    "dv_platform.analysis.review": {
        "_clock_reset_decisions",
        "_memory_cdc_decisions",
        "_verification_quality_decisions",
    },
    "dv_platform.analysis.rtl": {
        "_BLACK_BOX_SAFE_TARGETS",
        "_FEATURE_TARGETS",
        "_UNSUPPORTED_FEATURE_TAGS",
    },
    "dv_platform.core.config": {
        "Any",
        "_DEPTH_ALLOWED_PARAMETERS",
        "_ai_config",
        "_config_projection",
        "_config_records",
        "_validate_ai_endpoint",
        "_validate_coverage_and_profiles",
        "_validate_depth_and_plugins",
        "_validate_execution",
        "_validate_cdc_depth",
        "_validate_frontends_and_bindings",
        "_validate_formal_depth",
        "_validate_input_paths",
        "_validate_memory_depth",
        "_validate_parameter_modes",
        "_validate_parameter_sweeps",
        "_validate_parameters",
        "_parameter_override_name",
        "_validate_peripheral_depth",
        "_validate_plugin_publishers",
        "_validate_redaction_and_retention",
        "_validate_reset_depth",
        "_validate_security",
        "_validate_tool_selection",
    },
    "dv_platform.enterprise.adapters": {
        "_normalize_enterprise_result",
        "_run_enterprise_process",
        "_validate_invocation_environment",
        "_write_enterprise_summary",
        "_load_artifacts",
        "_load_checks",
    },
    "dv_platform.enterprise.cli": {
        "_benchmark",
        "_dispatch_command",
        "_dispatch_reporting_command",
        "_list_profiles",
        "_qualify_external_design",
        "_qualify",
        "_verify_evidence",
        "_verify_signature",
        "_write_signing_payload",
    },
    "dv_platform.enterprise.evidence": {
        "_pilot_signature_bundle",
        "_validate_pilot_record",
    },
    "dv_platform.enterprise.external_design": {
        "Any",
        "_decode_surelog_parameter",
        "_decode_surelog_port",
        "_external_design_inputs",
        "_external_design_payload",
        "_relationship_lines",
        "_run_external_surelog",
        "_run_external_verilator",
    },
    "dv_platform.enterprise.qualification": {
        "_load_qualification_policy",
        "_profile_qualification",
        "_record_identity",
    },
    "dv_platform.enterprise.requirements": {
        "_enterprise_requirement",
        "_exported_at",
        "_import_records",
        "_validated_record",
        "_validated_root",
    },
    "dv_platform.enterprise.store": {
        "_enterprise_failures",
        "_enterprise_runs",
    },
    "dv_platform.enterprise.signatures": {
        "_approved_signer",
        "_validate_signature_manifest",
        "_validate_signature_policy",
        "_verify_detached_signature",
    },
    "dv_platform.generators.formal": {
        "_cdc_report_payload",
        "_harness_presentation",
        "_sby_presentation",
    },
    "dv_platform.generators.artifacts": {
        "_artifact_persistence",
        "_validate_artifact_target",
        "_validate_artifact_traceability",
        "_validate_manifest_file_records",
        "_validate_manifest_project",
        "_validate_manifest_traceability",
    },
    "dv_platform.generators.cdc": {
        "VerificationScenario",
        "_cocotb_cdc_scenario",
        "_cocotb_cdc_scenarios",
    },
    "dv_platform.generators.cocotb": {
        "_append_scenario_lines",
        "_cocotb_check_context",
        "_cocotb_presentation",
    },
    "dv_platform.generators.uvm": {
        "_package_presentation",
        "_profile_uvm_presentation",
        "_protocol_uvm_presentation",
    },
    "dv_platform.generators.protocols": {
        "RegisterModel",
        "_cocotb_avalon_response",
        "_cocotb_model_probe",
        "_cocotb_packet_completion",
        "_cocotb_profile_handshake",
        "_cocotb_profile_scenario",
        "_cocotb_register_probe",
        "_cocotb_wishbone_response",
        "_formal_axi4_semantics",
        "_formal_profile_model_assertions",
        "_formal_profile_semantic_assertions",
        "_formal_wishbone_semantics",
        "_native_ahb_semantic_checks",
        "_native_avalon_mm_semantic_checks",
        "_native_avalon_st_semantic_checks",
        "_native_axi_semantic_checks",
        "_native_profile_task",
        "_native_stream_semantic_checks",
        "_native_tilelink_semantic_checks",
        "_native_wishbone_semantic_checks",
        "_sv_model_assertions",
        "_vhdl_profile_accesses",
        "_vhdl_profile_semantics",
    },
}


def _digest(value: object) -> str:
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _normalized_text(value: str) -> str:
    normalized = value.replace(str(ROOT), "<REPO>")
    normalized = re.sub(r"/tmp/[A-Za-z0-9_.-]+", "<TMP>", normalized)
    normalized = re.sub(r"\b[0-9a-f]{8}-[0-9a-f-]{27,}\b", "<UUID>", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"\brev-[0-9a-f]{8,}\b", "rev-<ID>", normalized)
    normalized = re.sub(
        r"\b20\d\d-\d\d-\d\d[T ][0-2]\d:[0-5]\d:[0-5]\d(?:\.\d+)?(?:Z|[+-]\d\d:\d\d)?\b",
        "<TIMESTAMP>",
        normalized,
    )
    return normalized


def _module_names() -> tuple[str, ...]:
    import dv_platform

    discovered = {dv_platform.__name__}
    discovered.update(item.name for item in pkgutil.walk_packages(dv_platform.__path__, "dv_platform."))
    return tuple(
        sorted(
            name
            for name in discovered
            if name == "dv_platform" or any(name == root or name.startswith(root + ".") for root in COMPATIBILITY_ROOTS)
            if not name.startswith(INTERNAL_IMPLEMENTATION_PREFIXES)
        )
    )


def _signature(value: object) -> str | None:
    if not callable(value):
        return None
    try:
        return re.sub(r"0x[0-9a-fA-F]+", "0x<ADDRESS>", str(inspect.signature(value)))
    except (TypeError, ValueError):
        return None


def _symbol_kind(value: object) -> str:
    if inspect.isclass(value):
        return "class"
    if inspect.isfunction(value):
        return "function"
    if inspect.ismodule(value):
        return "module"
    return type(value).__name__


def capture_module_contracts() -> dict[str, object]:
    contracts: dict[str, object] = {}
    for module_name in _module_names():
        module = importlib.import_module(module_name)
        symbols = {}
        for name, value in sorted(vars(module).items()):
            if name.startswith("__"):
                continue
            if name in ADDITIVE_INTERNAL_SYMBOLS.get(module_name, set()):
                continue
            if inspect.ismodule(value) and value.__name__.startswith(module.__name__ + "."):
                continue
            symbols[name] = {
                "kind": _symbol_kind(value),
                "signature": _signature(value),
            }
        contracts[module_name] = symbols
    return contracts


def capture_dataclass_contracts() -> dict[str, object]:
    from dv_platform.domain import models

    result = {}
    for name, value in sorted(vars(models).items()):
        if not inspect.isclass(value) or not dataclasses.is_dataclass(value):
            continue
        result[name] = {
            "lookup_module": value.__module__,
            "fields": [
                {
                    "name": field.name,
                    "type": str(field.type),
                    "has_default": field.default is not dataclasses.MISSING
                    or field.default_factory is not dataclasses.MISSING,
                }
                for field in dataclasses.fields(value)
            ],
        }
    return result


def _cli_case(arguments: Sequence[str], *, enterprise: bool = False) -> dict[str, object]:
    if enterprise:
        expression = "from dv_platform.enterprise.cli import main; raise SystemExit(main())"
        command = [sys.executable, "-c", expression, *arguments]
    else:
        command = [sys.executable, "-m", "dv_platform", *arguments]
    completed = subprocess.run(command, cwd=ROOT, check=False, capture_output=True, text=True)
    return {
        "arguments": list(arguments),
        "exit_code": completed.returncode,
        "stdout": _normalized_text(completed.stdout),
        "stderr": _normalized_text(completed.stderr),
    }


def capture_cli_contracts() -> dict[str, object]:
    return {
        "main_help": _cli_case(("--help",)),
        "main_invalid": _cli_case(("not-a-command",)),
        "enterprise_help": _cli_case(("--help",), enterprise=True),
    }


def capture_entry_points() -> dict[str, object]:
    project = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    return {
        "scripts": project.get("scripts", {}),
        "entry-points": project.get("entry-points", {}),
    }


def capture_schema_versions() -> dict[str, object]:
    result = {}
    for module_name in _module_names():
        module = importlib.import_module(module_name)
        versions = {
            name: value
            for name, value in vars(module).items()
            if name.isupper()
            and ("SCHEMA_VERSION" in name or name.endswith("_API_VERSION"))
            and isinstance(value, str | int)
        }
        if versions:
            result[module_name] = dict(sorted(versions.items()))
    return result


def capture_generated_artifacts() -> list[dict[str, object]]:
    from dv_platform.core.models import VerificationPlan, VerificationTarget
    from dv_platform.generators.cocotb import CocotbGenerator
    from dv_platform.generators.formal import FormalGenerator
    from dv_platform.generators.systemverilog import SystemVerilogGenerator
    from dv_platform.generators.uvm import UvmGenerator
    from dv_platform.generators.verilog import VerilogGenerator
    from dv_platform.generators.vhdl import VhdlGenerator

    plan = VerificationPlan("compatibility_top", tuple(VerificationTarget))
    backends = (
        CocotbGenerator(),
        FormalGenerator(),
        SystemVerilogGenerator(),
        UvmGenerator(),
        VerilogGenerator(),
        VhdlGenerator(),
    )
    records = []
    for backend in backends:
        for artifact in backend.generate(plan):
            records.append(
                {
                    "target": artifact.target.value,
                    "path": artifact.path.as_posix(),
                    "kind": artifact.kind.value,
                    "content_sha256": hashlib.sha256(artifact.content.encode("utf-8")).hexdigest(),
                    "content_bytes": len(artifact.content.encode("utf-8")),
                }
            )
    return sorted(records, key=lambda item: (str(item["target"]), str(item["path"])))


def capture_manifest() -> dict[str, object]:
    return {
        "format": "dv-platform-compatibility-contract-v1",
        "modules": capture_module_contracts(),
        "dataclasses": capture_dataclass_contracts(),
        "cli": capture_cli_contracts(),
        "entry_points": capture_entry_points(),
        "schemas": capture_schema_versions(),
        "artifacts": capture_generated_artifacts(),
    }


def fingerprints(manifest: Mapping[str, object]) -> dict[str, object]:
    sections = ("modules", "dataclasses", "cli", "entry_points", "schemas", "artifacts")
    return {
        "format": manifest["format"],
        "sections": {name: _digest(manifest[name]) for name in sections},
        "counts": {
            "modules": len(manifest["modules"]) if isinstance(manifest["modules"], Mapping) else 0,
            "dataclasses": len(manifest["dataclasses"]) if isinstance(manifest["dataclasses"], Mapping) else 0,
            "artifacts": len(manifest["artifacts"]) if isinstance(manifest["artifacts"], Sequence) else 0,
        },
        "overall": _digest(manifest),
    }


def compare(expected: Mapping[str, Any], actual: Mapping[str, Any]) -> tuple[str, ...]:
    errors = []
    if expected.get("format") != actual.get("format"):
        errors.append(f"format changed: {expected.get('format')!r} -> {actual.get('format')!r}")
    expected_sections = expected.get("sections", {})
    actual_sections = actual.get("sections", {})
    if isinstance(expected_sections, Mapping) and isinstance(actual_sections, Mapping):
        for name in sorted(set(expected_sections) | set(actual_sections)):
            if expected_sections.get(name) != actual_sections.get(name):
                errors.append(f"{name} compatibility fingerprint changed")
    return tuple(errors)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, default=DEFAULT_BASELINE)
    parser.add_argument("--check", action="store_true")
    parser.add_argument("--manifest", action="store_true", help="print the full normalized manifest")
    args = parser.parse_args()
    manifest = capture_manifest()
    actual = fingerprints(manifest)
    if args.manifest:
        print(json.dumps(manifest, indent=2, sort_keys=True))
        return 0
    if not args.check:
        print(json.dumps(actual, indent=2, sort_keys=True))
        return 0
    expected = json.loads(args.baseline.read_text(encoding="utf-8"))
    errors = compare(expected, actual)
    if errors:
        for error in errors:
            print(error)
        return 1
    print(f"compatibility contract passed ({actual['overall']})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
