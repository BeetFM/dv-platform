"""Source isolation, document preservation, and rejection of stale RTL edits."""

import shutil
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.enterprise.equivalence import prove_equivalence
from dv_platform.enterprise.rtl import materialize_candidate, prove_rtl_candidate, snapshot_rtl


class RTLCandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.source = self.root / "source"
        self.source.mkdir()
        (self.source / "top.sv").write_text("module top(input a, output y); assign y = a & a; endmodule\n")
        (self.source / "design.md").write_text("Output y must equal input a in the same cycle.\n")
        self.snapshot = self.root / "snapshot"
        self.record = snapshot_rtl(self.source, ["top.sv"], ["design.md"], self.snapshot)

    def test_candidate_preserves_original_and_design_contract(self) -> None:
        output = self.root / "candidate"
        result = materialize_candidate(
            self.snapshot, self.record, [{"path": "top.sv", "before": "a & a", "after": "a"}], output
        )
        self.assertIn("a & a", (self.source / "top.sv").read_text())
        self.assertIn("a & a", (self.snapshot / "inputs/top.sv").read_text())
        self.assertIn("assign y = a;", (output / "inputs/top.sv").read_text())
        self.assertEqual(result["baseline_sha256"]["design.md"], result["candidate_sha256"]["design.md"])
        self.assertEqual(result["status"], "unverified")
        self.assertFalse(result["signoff_approved"])

    def test_rejects_document_edit_stale_match_and_unknown_file(self) -> None:
        for path, before in (("design.md", "Output"), ("top.sv", "missing"), ("../top.sv", "a & a")):
            with self.subTest(path=path, before=before), self.assertRaises(ValueError):
                materialize_candidate(
                    self.snapshot,
                    self.record,
                    [{"path": path, "before": before, "after": "changed"}],
                    self.root / "rejected",
                )
        self.assertFalse((self.root / "rejected").exists())

    def test_tampering_invalidates_snapshot(self) -> None:
        (self.snapshot / "inputs/design.md").write_text("Relaxed requirements")
        with self.assertRaisesRegex(ValueError, "changed after capture"):
            materialize_candidate(
                self.snapshot,
                self.record,
                [{"path": "top.sv", "before": "a & a", "after": "a"}],
                self.root / "candidate",
            )

    def test_rejects_traversal_and_symlinks(self) -> None:
        (self.source / "linked.sv").symlink_to(self.source / "top.sv")
        for name in ("../source/top.sv", "linked.sv", "./top.sv", "/top.sv"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                snapshot_rtl(self.source, [name], ["design.md"], self.root / "rejected")

    def test_ambiguous_replacement_is_rejected(self) -> None:
        with self.assertRaisesRegex(ValueError, "exactly once"):
            materialize_candidate(
                self.snapshot,
                self.record,
                [{"path": "top.sv", "before": "a", "after": "b"}],
                self.root / "candidate",
            )

    def test_normalized_paths_and_external_file_directives_are_required(self) -> None:
        for name in ("nested//top.sv", "top.sv/", "top\n.sv"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                snapshot_rtl(self.source, [name], ["design.md"], self.root / "bad-snapshot")
        with self.assertRaisesRegex(ValueError, "directives"):
            materialize_candidate(
                self.snapshot,
                self.record,
                [{"path": "top.sv", "before": "a & a", "after": 'a; `include "external.v"'}],
                self.root / "bad-directive",
            )

    @unittest.skipUnless(shutil.which("yosys") and shutil.which("prlimit"), "native Yosys is unavailable")
    def test_native_interface_latency_and_clock_mutations_are_rejected(self) -> None:
        reference = self.root / "reference.v"
        reference.write_text(
            "module top(input clk,a,output reg y,output z); always @(posedge clk) y<=a; assign z=~a; endmodule\n"
        )
        mutations = {
            "missing_output": "module top(input clk,a,output reg y); always @(posedge clk) y<=a; endmodule",
            "extra_latency": "module top(input clk,a,output reg y,output z); reg delayed; "
            "always @(posedge clk) begin delayed<=a; y<=delayed; end assign z=~a; endmodule",
            "wrong_clock": "module top(input clk,a,output reg y,output z); "
            "always @(negedge clk) y<=a; assign z=~a; endmodule",
        }
        for label, text in mutations.items():
            candidate = self.root / f"{label}.v"
            candidate.write_text(text)
            with self.subTest(label=label), self.assertRaises(ValueError):
                prove_equivalence(reference, candidate, [], "top", self.root / label, ports_only=True)

    @unittest.skipUnless(shutil.which("yosys") and shutil.which("prlimit"), "native Yosys is unavailable")
    def test_native_proof_accepts_rewrite_and_rejects_wrong_output(self) -> None:
        for after, expected in (("a", "equivalent"), ("~a", "rejected")):
            with self.subTest(after=after):
                result = prove_rtl_candidate(
                    self.snapshot,
                    self.record,
                    [{"path": "top.sv", "before": "a & a", "after": after}],
                    "top",
                    self.root / expected,
                )
                self.assertEqual(result["status"], expected, result.get("error"))
                self.assertFalse(result["signoff_approved"])
