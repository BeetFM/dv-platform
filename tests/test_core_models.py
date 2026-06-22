from pathlib import Path
import unittest

from dv_platform.analysis import create_initial_plan
from dv_platform.core.models import (
    ClaimStatus,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLProject,
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


if __name__ == "__main__":
    unittest.main()
