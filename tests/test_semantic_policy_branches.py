import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.analysis.semantic_crosscheck import (
    CAPABILITY_DESIGN_UNITS,
    CAPABILITY_IMPORTS,
    CAPABILITY_PORTS,
    COMPARABLE_CAPABILITIES,
    CapabilityCoverage,
    FrontendMetadata,
    NormalizedFactCrossChecker,
    SemanticCrossCheckIssue,
    SemanticCrossCheckResult,
    SlangAnalyzer,
    SlangRunError,
    aggregate_crosscheck_results,
    capabilities_for_modules,
    classify_slang_version,
    required_capabilities_for_modules,
    unavailable_crosscheck_result,
    write_crosscheck_result,
)
from dv_platform.core.models import EvidenceKind, EvidenceRef, RTLModule, RTLPort


class SemanticPolicyBranchTests(unittest.TestCase):
    def test_capability_matrix_distinguishes_missing_primary_and_reference(self) -> None:
        module = RTLModule("top")
        checker = NormalizedFactCrossChecker(
            primary_capabilities=(CAPABILITY_DESIGN_UNITS, CAPABILITY_PORTS),
            reference_capabilities=(CAPABILITY_DESIGN_UNITS, CAPABILITY_IMPORTS),
            required_capabilities=(CAPABILITY_PORTS, CAPABILITY_IMPORTS),
            unsupported_reasons={CAPABILITY_PORTS: "reference mapper omitted ports"},
        )

        result = checker.compare((module,), (module,))
        statuses = {item.capability: item.status for item in result.capabilities}

        self.assertEqual(statuses[CAPABILITY_PORTS], "unsupported")
        self.assertEqual(statuses[CAPABILITY_IMPORTS], "missing_primary")
        self.assertEqual({issue.capability for issue in result.issues}, {CAPABILITY_PORTS, CAPABILITY_IMPORTS})
        self.assertIn(CAPABILITY_PORTS, result.unsupported_capabilities)

    def test_duplicate_and_missing_specializations_fail_closed(self) -> None:
        primary = RTLModule("primary", original_name="top")
        duplicate = RTLModule("duplicate", original_name="top")
        reference = RTLModule("reference", original_name="top")
        checker = NormalizedFactCrossChecker(
            primary_capabilities=(CAPABILITY_DESIGN_UNITS,),
            reference_capabilities=(CAPABILITY_DESIGN_UNITS,),
            required_capabilities=(),
        )

        duplicate_result = checker.compare((primary, duplicate), (reference,))
        missing_result = checker.compare((), (reference,))

        self.assertEqual(duplicate_result.issues[0].field, "specialization_identity")
        self.assertEqual(duplicate_result.issues[0].primary, "2")
        self.assertEqual(missing_result.issues[0].field, "module")
        self.assertEqual(missing_result.issues[0].primary, "0")

    def test_comparisons_obey_capability_selection_and_include_locations(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vtop.xml", "module:top"),)
        primary = RTLModule(
            "top",
            source=Path("primary.sv"),
            ports=("a",),
            port_details=(RTLPort("a", "input", width=8, source_location="primary.sv:2"),),
            imports=("pkg_a::*",),
            ast_refs=evidence,
        )
        reference = RTLModule(
            "top",
            source=Path("reference.sv"),
            ports=("b",),
            port_details=(RTLPort("b", "output", width=16, source_location="reference.sv:4"),),
            imports=("pkg_b::*",),
            ast_refs=evidence,
        )
        capabilities = (CAPABILITY_DESIGN_UNITS, CAPABILITY_PORTS, CAPABILITY_IMPORTS)

        result = NormalizedFactCrossChecker(
            primary_capabilities=capabilities,
            reference_capabilities=capabilities,
            required_capabilities=capabilities,
        ).compare((primary,), (reference,))

        self.assertEqual({issue.field for issue in result.issues}, {"ports", "port_details", "imports"})
        detail = next(issue for issue in result.issues if issue.field == "port_details")
        self.assertEqual((detail.primary_location, detail.reference_location), ("primary.sv:2", "reference.sv:4"))

    def test_aggregation_preserves_failure_unavailability_and_capability_reasons(self) -> None:
        checked = tuple(CapabilityCoverage(item, "checked", True) for item in COMPARABLE_CAPABILITIES)
        passed = SemanticCrossCheckResult("verilator", "slang", ("top",), capabilities=checked)
        failed = SemanticCrossCheckResult(
            "verilator",
            "slang",
            ("other",),
            (SemanticCrossCheckIssue("other", "ports", "a", "b"),),
            status="failed",
            capabilities=(CapabilityCoverage(CAPABILITY_PORTS, "unsupported", True, "gap"),),
            unsupported_capabilities=(CAPABILITY_PORTS,),
        )
        unavailable = unavailable_crosscheck_result(
            "run-3", FrontendMetadata("verilator", "5.020"), FrontendMetadata("slang"), "not installed"
        )

        failed_aggregate = aggregate_crosscheck_results((passed, failed))
        unavailable_aggregate = aggregate_crosscheck_results((passed, unavailable))

        self.assertEqual(failed_aggregate.status, "failed")
        self.assertEqual(failed_aggregate.checked_modules, ("top", "other"))
        ports = next(item for item in failed_aggregate.capabilities if item.capability == CAPABILITY_PORTS)
        self.assertEqual((ports.status, ports.reason), ("unsupported", "gap"))
        self.assertEqual(unavailable_aggregate.status, "unavailable")
        self.assertFalse(unavailable.passed)
        with self.assertRaisesRegex(ValueError, "At least one"):
            aggregate_crosscheck_results(())

    def test_slang_version_and_declared_profiles_are_stable(self) -> None:
        self.assertEqual(classify_slang_version(None)["status"], "unsupported")
        self.assertIsNone(classify_slang_version("development build")["major"])
        supported = classify_slang_version("slang 11.4.0")
        self.assertEqual((supported["status"], supported["major"]), ("supported", 11))
        self.assertEqual(classify_slang_version("slang 999.0")["status"], "unsupported")
        self.assertEqual(capabilities_for_modules(()), COMPARABLE_CAPABILITIES)
        self.assertEqual(required_capabilities_for_modules(()), COMPARABLE_CAPABILITIES)

    def test_unavailable_slang_persists_evidence_and_analyze_raises(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            analyzer = SlangAnalyzer("definitely-missing-slang", redact=lambda value: value.replace("missing", "x"))
            command = analyzer.build_command(
                (root / "top.sv",),
                root / "ast.json",
                top_modules=("top",),
                include_paths=(root / "include",),
                defines=("WIDTH=8",),
                parameter_overrides=("top.WIDTH=16",),
            )
            self.assertIn("--top", command)
            self.assertIn("-G", command)
            self.assertIn(f"-I{root / 'include'}", command)
            with patch("dv_platform.analysis.semantic_crosscheck.subprocess.run", side_effect=OSError("missing tool")):
                result = analyzer.run((), root / "out" / "ast.json")
            self.assertFalse(result.succeeded)
            self.assertIsNone(result.return_code)
            self.assertIn("x tool", result.error or "")
            diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "unavailable")

            with patch("dv_platform.analysis.semantic_crosscheck.subprocess.run", side_effect=OSError("missing tool")):
                with self.assertRaises(SlangRunError):
                    analyzer.analyze((), root / "other" / "ast.json")

    def test_result_serialization_includes_issue_evidence_and_nullable_frontends(self) -> None:
        evidence = EvidenceRef(EvidenceKind.SLANG_AST, "ast.json", "top.sv:4", "port mismatch")
        result = SemanticCrossCheckResult(
            "verilator",
            "slang",
            (),
            (
                SemanticCrossCheckIssue(
                    "top",
                    "ports",
                    "a",
                    "b",
                    primary_evidence=(evidence,),
                    reference_evidence=(evidence,),
                    primary_location="top.sv:4",
                ),
            ),
            status="failed",
        )
        with TemporaryDirectory() as temp_dir:
            path = write_crosscheck_result(Path(temp_dir) / "nested" / "result.json", result)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertIsNone(payload["primary"])
        self.assertEqual(payload["issues"][0]["primary_evidence"][0]["kind"], "slang_ast")
        self.assertEqual(payload["issues"][0]["primary_location"], "top.sv:4")


if __name__ == "__main__":
    unittest.main()
