"""Complete state-transition proofs reject functional and clock changes."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.enterprise.native import run_native
from dv_platform.enterprise.transition_equivalence import (
    UnsupportedStateCorrespondence,
    _state_pairs,
    prove_mapped_equivalence,
    prove_transition_equivalence,
)
from dv_platform.signoff import verify_artifacts

RTL = """module block(input clk,other,rst,input [3:0] d,output [3:0] q);
reg [3:0] count;
assign q=count;
always @(posedge clk) if(rst)count<=0;else count<=count+d;
endmodule
"""


class StatePairAliasTests(TestCase):
    def models(self):
        def model(names):
            return {"netnames": {name: {"hide_name": 0, "bits": bits} for name, bits in names.items()}}

        return (
            model({"count": [10, 11], "_0042_": [10]}),
            model({"count": [20, 21], "_0042_": [21]}),
            {"gold": {10: None, 11: None}, "gate": {20: None, 21: None}},
        )

    def test_source_aliases_take_priority_over_recycled_generated_names(self):
        self.assertEqual(_state_pairs(*self.models()), [(10, 20), (11, 21)])

    def test_conflicting_source_aliases_remain_unsupported(self):
        gold, gate, registers = self.models()
        gold["netnames"]["source_alias"] = {"hide_name": 0, "bits": [10]}
        gate["netnames"]["source_alias"] = {"hide_name": 0, "bits": [21]}
        with self.assertRaisesRegex(UnsupportedStateCorrespondence, "ambiguous"):
            _state_pairs(gold, gate, registers)

    def test_generated_only_state_keeps_complete_bijective_fallback(self):
        gold, gate, registers = self.models()
        del gold["netnames"]["count"]
        del gate["netnames"]["count"]
        gate["netnames"]["_0042_"]["bits"] = [20]
        gold["netnames"]["u._0050_.Q"] = {"hide_name": 0, "bits": [11]}
        gate["netnames"]["u._0050_.Q"] = {"hide_name": 0, "bits": [21]}
        self.assertEqual(_state_pairs(gold, gate, registers), [(10, 20), (11, 21)])
        gate["netnames"]["u._0050_.Q"]["bits"] = [20]
        with self.assertRaisesRegex(UnsupportedStateCorrespondence, "complete and bijective"):
            _state_pairs(gold, gate, registers)


@skipUnless(shutil.which("yosys") and shutil.which("prlimit"), "requires native Yosys")
class TransitionEquivalenceTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.gold = self.root / "gold.v"
        self.gate = self.root / "gate.v"
        self.gold.write_text(RTL)

    def prove(self, source, label):
        self.gate.write_text(source)
        return prove_transition_equivalence(self.gold, self.gate, [], "block", self.root / label, timeout=30)

    def test_full_state_proof_and_functional_mutations(self):
        result = self.prove(RTL.replace("count+d", "count+d+4'd0"), "positive")
        self.assertEqual(result["proven_output_bits"], 4)
        self.assertEqual(result["proven_next_state_bits"], 4)
        self.assertEqual(result["clock"], ("clk", 0))
        for name, source in (
            ("arithmetic", RTL.replace("count+d", "count-d")),
            ("reset", RTL.replace("count<=0", "count<=1")),
            ("output", RTL.replace("q=count", "q=~count")),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, "native equivalence failed"):
                self.prove(source, name)
            self.assertFalse((self.root / name / "proof.json").exists())

    def test_native_recycled_aliases_do_not_hide_a_functional_mutation(self):
        source = RTL.replace("assign q=count;", "wire _0042_=count[0];\nassign q=count;")
        self.gold.write_text(source)
        candidate = source.replace("_0042_=count[0]", "_0042_=count[1]")
        result = self.prove(candidate, "recycled-alias")
        self.assertEqual(result["proven_next_state_bits"], 4)
        with self.assertRaisesRegex(ValueError, "native equivalence failed"):
            self.prove(candidate.replace("count+d", "count-d"), "recycled-alias-mutation")

    def test_redundant_enabled_sign_registers_are_normalized_before_matching(self):
        reference = """module block(input clk,en,rst,d,output reg [7:0] q);
always @(posedge clk) if(rst)q<=0;else if(en)q<={8{d}};
endmodule
"""
        candidate = """module block(input clk,en,rst,d,output [7:0] q);
reg sign_bit;
always @(posedge clk) if(rst)sign_bit<=0;else if(en)sign_bit<=d;
assign q={8{sign_bit}};
endmodule
"""
        self.gold.write_text(reference)
        self.gate.write_text(candidate)
        result = prove_transition_equivalence(self.gold, self.gate, [], "block", self.root / "sign", timeout=30)
        self.assertEqual(result["proven_output_bits"], 8)
        self.assertEqual(result["proven_next_state_bits"], 1)

    def test_clock_and_initial_state_cannot_be_assumed(self):
        for name, source, message in (
            ("edge", RTL.replace("posedge", "negedge"), "rising-edge"),
            ("clock", RTL.replace("posedge clk", "posedge other"), "identical primary clock"),
            ("init", RTL.replace("assign q", "initial count=3;\nassign q"), "initialized"),
            ("state", RTL.replace("reg [3:0] count", "reg [2:0] count"), "correspondence"),
        ):
            with self.subTest(name=name), self.assertRaisesRegex(ValueError, message):
                self.prove(source, name)
            self.assertFalse((self.root / name / "proof.json").exists())

    def test_prepared_model_tampering_prevents_a_proof(self):
        def tamper(*args, **kwargs):
            receipt = run_native(*args, **kwargs)
            if args[2] == "prepare-gold":
                (args[1] / "gold.json").write_text("{}")
            return receipt

        with patch("dv_platform.enterprise.transition_equivalence.run_native", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.prove(RTL, "tamper")
        self.assertFalse((self.root / "tamper/proof.json").exists())

    def test_initialized_equivalent_design_uses_clock_event_fallback(self):
        source = RTL.replace("assign q", "initial count=3;\nassign q")
        self.gold.write_text(source)
        self.gate.write_text(source)
        output = self.root / "fallback"
        result = prove_mapped_equivalence(self.gold, self.gate, [], "block", output, timeout=30)
        self.assertEqual(result["status"], "passed")
        self.assertIn("initialized", result["transition_fallback_reason"])
        self.assertTrue((output / "clock-events/proof.json").is_file())
        verify_artifacts(output, result["artifacts"])

    def test_a_failed_transition_proof_never_falls_back(self):
        self.gate.write_text(RTL.replace("count+d", "count-d"))
        with patch("dv_platform.enterprise.equivalence.prove_equivalence") as fallback:
            with self.assertRaisesRegex(ValueError, "native equivalence failed"):
                prove_mapped_equivalence(self.gold, self.gate, [], "block", self.root / "negative", timeout=30)
            fallback.assert_not_called()

    def test_wrong_clock_edge_is_rejected_by_the_fallback(self):
        self.gate.write_text(RTL.replace("posedge", "negedge"))
        output = self.root / "wrong-clock"
        with self.assertRaisesRegex(ValueError, "native equivalence failed"):
            prove_mapped_equivalence(self.gold, self.gate, [], "block", output, timeout=30)
        self.assertFalse((output / "proof.json").exists())
        self.assertIn("unproven $equiv", (output / "clock-events/equivalence.stderr.log").read_text())
