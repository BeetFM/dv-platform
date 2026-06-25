from pathlib import Path
import unittest

from dv_platform.analysis import create_initial_plan, gate_generation
from dv_platform.analysis.docs import LoadedDocument, chunk_document
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLProject,
    Severity,
    VerificationTarget,
)


class CoreModelTests(unittest.TestCase):
    def test_project_finds_module_by_name(self) -> None:
        module = RTLModule(name="uart_rx")
        project = RTLProject(root=Path("."), modules=[module])

        self.assertEqual(project.module_by_name("uart_rx"), module)
        self.assertIsNone(project.module_by_name("uart_tx"))

    def test_initial_plan_records_clock_reset_and_port_checks(self) -> None:
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n", "data_i", "data_o"),
            clocks=("clk",),
            resets=("rst_n",),
        )

        plan = create_initial_plan(
            module,
            targets=(VerificationTarget.COCOTB, VerificationTarget.FORMAL),
        )

        self.assertEqual(plan.module, "fifo")
        self.assertEqual(plan.targets, (VerificationTarget.COCOTB, VerificationTarget.FORMAL))
        self.assertIn("Drive declared clock inputs with stable periods.", plan.checks)
        self.assertIn("Exercise reset assertion and deassertion sequencing.", plan.checks)
        self.assertEqual(plan.open_questions, ())

    def test_initial_plan_claims_can_reference_verilator_ast_evidence(self) -> None:
        ast_ref = EvidenceRef(
            kind=EvidenceKind.VERILATOR_AST,
            source_id="verilator:obj_dir/Vtop.xml",
            locator="module:fifo",
            summary="fifo module declaration",
        )
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n"),
            clocks=("clk",),
            resets=("rst_n",),
            ast_refs=(ast_ref,),
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,))

        self.assertEqual(len(plan.claims), 2)
        self.assertTrue(all(claim.status == ClaimStatus.SUPPORTED for claim in plan.claims))
        self.assertTrue(all(claim.evidence_refs == (ast_ref,) for claim in plan.claims))
        self.assertEqual(plan.claims[0].claim_type, ClaimType.RTL_STRUCTURE)
        self.assertEqual(plan.claims[0].severity, Severity.HIGH)
        self.assertTrue(plan.claims[0].generation_precondition)

    def test_initial_plan_attaches_retrieved_documentation_evidence(self) -> None:
        module = RTLModule(
            name="simple_counter",
            ports=("clk", "rst_n", "enable_i", "count_o"),
        )
        chunks = chunk_document(
            LoadedDocument(
                source=Path("docs/counter.md"),
                text="The simple_counter increments count_o when enable_i is asserted.",
            )
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,), documentation_chunks=chunks)

        self.assertEqual(plan.requirements, ("The simple_counter increments count_o when enable_i is asserted.",))
        documentation_claims = [claim for claim in plan.claims if claim.claim_id == "simple_counter:documentation-intent"]
        self.assertEqual(len(documentation_claims), 1)
        self.assertEqual(documentation_claims[0].status, ClaimStatus.SUPPORTED)
        self.assertEqual(documentation_claims[0].claim_type, ClaimType.DOCUMENTATION_INTENT)
        self.assertEqual(documentation_claims[0].evidence_refs[0].kind, EvidenceKind.DOCUMENT_CHUNK)
        self.assertTrue(documentation_claims[0].evidence_refs[0].locator.startswith("chunk:doc:"))

    def test_initial_plan_records_open_question_when_documentation_does_not_match(self) -> None:
        module = RTLModule(name="uart_rx", ports=("clk", "data_i"))
        chunks = chunk_document(
            LoadedDocument(
                source=Path("docs/counter.md"),
                text="The counter increments when enable is asserted.",
            )
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,), documentation_chunks=chunks)

        self.assertIn("No documentation intent was retrieved for this module.", plan.open_questions)

    def test_initial_plan_claims_can_gate_generation(self) -> None:
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n"),
            clocks=("clk",),
            resets=("rst_n",),
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,))
        gate = gate_generation(plan.claims, strict=True)

        self.assertFalse(gate.allowed)
        self.assertTrue(any(validation.claim.claim_id == "fifo:clocking" for validation in gate.blocked))


if __name__ == "__main__":
    unittest.main()
