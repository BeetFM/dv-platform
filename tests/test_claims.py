import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.claims import (
    ClaimAction,
    check_ast_claim,
    check_documentation_claim,
    claim_report_json,
    claim_report_markdown,
    classify_claim_validation,
    gate_generation,
    with_claim_status,
    write_claim_reports,
)
from dv_platform.core.models import ClaimStatus, EvidenceKind, EvidenceRef, Severity, VerificationClaim


class ClaimPolicyTests(unittest.TestCase):
    def test_supported_claim_is_allowed(self) -> None:
        claim = VerificationClaim("c1", "fifo", "clock exists", status=ClaimStatus.SUPPORTED)

        validation = classify_claim_validation(claim)

        self.assertEqual(validation.action, ClaimAction.ALLOW)

    def test_critical_unsupported_claim_blocks(self) -> None:
        claim = VerificationClaim("c1", "fifo", "reset exists", severity=Severity.CRITICAL)

        validation = classify_claim_validation(claim)

        self.assertEqual(validation.action, ClaimAction.BLOCK)

    def test_high_missing_claim_warns_locally_and_blocks_in_strict_mode(self) -> None:
        claim = VerificationClaim(
            "c1",
            "fifo",
            "transaction intent exists",
            severity=Severity.HIGH,
            status=ClaimStatus.MISSING_EVIDENCE,
        )

        self.assertEqual(classify_claim_validation(claim, strict=False).action, ClaimAction.WARN)
        self.assertEqual(classify_claim_validation(claim, strict=True).action, ClaimAction.BLOCK)

    def test_high_contradicted_claim_blocks(self) -> None:
        claim = VerificationClaim(
            "c1",
            "fifo",
            "active high reset",
            severity=Severity.HIGH,
            status=ClaimStatus.CONTRADICTED,
        )

        validation = classify_claim_validation(claim)

        self.assertEqual(validation.action, ClaimAction.BLOCK)

    def test_medium_generation_precondition_blocks(self) -> None:
        claim = VerificationClaim(
            "c1",
            "fifo",
            "clock used by generated test",
            generation_precondition=True,
            status=ClaimStatus.UNCHECKED,
        )

        validation = classify_claim_validation(claim)

        self.assertEqual(validation.action, ClaimAction.BLOCK)

    def test_low_missing_claim_is_annotated(self) -> None:
        claim = VerificationClaim("c1", "fifo", "style preference", severity=Severity.LOW)

        validation = classify_claim_validation(claim)

        self.assertEqual(validation.action, ClaimAction.ANNOTATE)

    def test_with_claim_status_returns_updated_copy(self) -> None:
        claim = VerificationClaim("c1", "fifo", "clock exists")

        updated = with_claim_status(claim, ClaimStatus.SUPPORTED)

        self.assertEqual(updated.status, ClaimStatus.SUPPORTED)
        self.assertEqual(claim.status, ClaimStatus.UNCHECKED)


class ClaimCheckerTests(unittest.TestCase):
    def test_ast_claim_is_supported_when_ast_evidence_is_available(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vtop.xml", "module:top")
        claim = VerificationClaim("c1", "top", "top exists", evidence_refs=(ref,))

        checked = check_ast_claim(claim, available_source_ids=("Vtop.xml",))

        self.assertEqual(checked.status, ClaimStatus.SUPPORTED)
        self.assertEqual(checked.evidence_refs, (ref,))

    def test_ast_claim_missing_when_required_evidence_kind_is_absent(self) -> None:
        ref = EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/top.md", "chunk:1")
        claim = VerificationClaim("c1", "top", "top exists", evidence_refs=(ref,))

        checked = check_ast_claim(claim)

        self.assertEqual(checked.status, ClaimStatus.MISSING_EVIDENCE)

    def test_documentation_claim_missing_when_source_is_unavailable(self) -> None:
        ref = EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/top.md", "chunk:1")
        claim = VerificationClaim("c1", "top", "docs exist", evidence_refs=(ref,))

        checked = check_documentation_claim(claim, available_source_ids=("docs/other.md",))

        self.assertEqual(checked.status, ClaimStatus.MISSING_EVIDENCE)
        self.assertEqual(checked.evidence_refs, (ref,))

    def test_documentation_claim_can_be_deterministically_contradicted(self) -> None:
        ref = EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/top.md", "chunk:1")
        claim = VerificationClaim("c1", "top", "reset is active high", evidence_refs=(ref,))

        checked = check_documentation_claim(claim, contradicted_source_ids=("docs/top.md",))

        self.assertEqual(checked.status, ClaimStatus.CONTRADICTED)
        self.assertEqual(checked.evidence_refs, (ref,))


class GenerationGateTests(unittest.TestCase):
    def test_generation_gate_allows_supported_and_warning_only_claims(self) -> None:
        supported = VerificationClaim("c1", "top", "top exists", status=ClaimStatus.SUPPORTED)
        warning = VerificationClaim("c2", "top", "docs exist", severity=Severity.HIGH)

        gate = gate_generation((supported, warning), strict=False)

        self.assertTrue(gate.allowed)
        self.assertEqual(len(gate.warnings), 1)
        self.assertEqual(gate.blocked, ())

    def test_generation_gate_blocks_critical_claims(self) -> None:
        critical = VerificationClaim("c1", "top", "clock exists", severity=Severity.CRITICAL)

        gate = gate_generation((critical,))

        self.assertFalse(gate.allowed)
        self.assertEqual(gate.blocked[0].claim, critical)

    def test_generation_gate_blocks_high_missing_claims_in_strict_mode(self) -> None:
        high = VerificationClaim("c1", "top", "docs exist", severity=Severity.HIGH)

        gate = gate_generation((high,), strict=True)

        self.assertFalse(gate.allowed)
        self.assertEqual(gate.blocked[0].action, ClaimAction.BLOCK)


class ClaimReportTests(unittest.TestCase):
    def test_claim_report_json_serializes_gate_and_evidence(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vtop.xml", "module:top", "top module")
        claim = VerificationClaim(
            "c1",
            "top",
            "top exists",
            severity=Severity.CRITICAL,
            evidence_refs=(ref,),
        )
        gate = gate_generation((claim,))

        payload = json.loads(claim_report_json(gate))

        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["blocked_count"], 1)
        self.assertEqual(payload["validations"][0]["claim_id"], "c1")
        self.assertEqual(payload["validations"][0]["evidence_refs"][0]["locator"], "module:top")

    def test_claim_report_markdown_contains_summary_and_validation_rows(self) -> None:
        claim = VerificationClaim("c1", "top", "clock exists", severity=Severity.CRITICAL)
        gate = gate_generation((claim,))

        markdown = claim_report_markdown(gate)

        self.assertIn("# Claim Report", markdown)
        self.assertIn("- allowed: false", markdown)
        self.assertIn("| block | unchecked | critical | c1 | critical claim is unchecked |", markdown)

    def test_write_claim_reports_writes_json_and_markdown(self) -> None:
        claim = VerificationClaim("c1", "top", "clock exists", status=ClaimStatus.SUPPORTED)
        gate = gate_generation((claim,))

        with TemporaryDirectory() as temp_dir:
            json_path, markdown_path = write_claim_reports(gate, Path(temp_dir))

            self.assertTrue(json_path.is_file())
            self.assertTrue(markdown_path.is_file())
            self.assertTrue(json.loads(json_path.read_text(encoding="utf-8"))["allowed"])
            self.assertIn("# Claim Report", markdown_path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
