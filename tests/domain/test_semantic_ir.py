import json
import unittest
from pathlib import Path

from dv_platform.agent.semantic import (
    SemanticBranch,
    SemanticExpression,
    SemanticIR,
    executable_semantics,
    generation_blockers,
)
from dv_platform.core.models import EvidenceKind, EvidenceRef


class SemanticIRTests(unittest.TestCase):
    def test_expression_width_signedness_truncation_and_extension_are_retained(self) -> None:
        cases = json.loads((Path(__file__).parent / "fixtures" / "semantic" / "semantic_cases.json").read_text())
        expressions = tuple(
            SemanticExpression(
                operator=name, width=value["width"], signed=value["signed"], cast=value.get("cast", "unknown")
            )
            for name, value in cases.items()
        )
        self.assertEqual(expressions[0].signed, True)
        self.assertEqual(expressions[2].cast, "packed[7:0]")
        self.assertEqual(expressions[3].cast, "zero_extend")

    def test_nested_branches_and_generate_conditions_keep_unknowns_explicit(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "top.xml", "branch:1")
        ir = SemanticIR(
            "top",
            expressions=(SemanticExpression("add", 8, False, evidence_refs=(ref,)),),
            branches=(SemanticBranch(None, "if.then", mutually_exclusive="unknown", evidence_refs=(ref,)),),
            generate_conditions=(SemanticExpression("eq", 1, False, evidence_refs=(ref,)),),
            evidence_refs=(ref,),
        )
        self.assertFalse(executable_semantics(ir, {"top.xml"}))
        self.assertIn("missing branch condition: if.then", generation_blockers(ir))

    def test_unknown_evidence_is_rejected_and_unknown_operator_blocks_generation(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "top.xml", "expr:1")
        ir = SemanticIR("top", expressions=(SemanticExpression("unknown", evidence_refs=(ref,)),))
        with self.assertRaisesRegex(ValueError, "unknown evidence"):
            ir.validate({"other.xml"})
        self.assertFalse(executable_semantics(ir, {"top.xml"}))


if __name__ == "__main__":
    unittest.main()
