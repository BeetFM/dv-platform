"""Pinned conversion preserves source scope, macro policy, and native evidence."""

import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.enterprise.rtl import lower_rtl_sources, materialize_candidate, prove_rtl_candidate, snapshot_rtl
from dv_platform.enterprise.rtl_frontend import convert_sources, freeze_frontend, validate_frontend
from dv_platform.physical_design import file_digest

SV2V = shutil.which("sv2v")


class RTLFrontendTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        (self.root / "converter").write_text("synthetic converter")
        self.spec = {
            "kind": "sv2v",
            "executable": "converter",
            "sha256": file_digest(self.root / "converter"),
            "defines": ["SYNTHESIS"],
        }
        (self.root / "types.sv").write_text("package types; typedef logic [7:0] byte_t; endpackage\n")
        (self.root / "top.sv").write_text(
            "module top(input types::byte_t a, output types::byte_t y); assign y=a & a; endmodule\n"
        )
        (self.root / "design.md").write_text("Output equals input in the same cycle.")

    def test_pin_and_macro_validation_precede_native_execution(self):
        for changes in ({"sha256": "0" * 64}, {"defines": []}, {"defines": ["SYNTHESIS", "../bad"]}, {"kind": "shell"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                validate_frontend(self.root, {**self.spec, **changes})
        frozen = freeze_frontend(self.root, self.spec, self.root / "frontend")
        (self.root / "converter").write_text("changed external converter")
        self.assertEqual(file_digest(Path(frozen["executable"])), self.spec["sha256"])
        Path(frozen["executable"]).write_text("tampered frozen binary")
        with (
            patch("dv_platform.enterprise.rtl_frontend.run_native") as run,
            self.assertRaisesRegex(ValueError, "changed"),
        ):
            convert_sources(self.root, ["top.sv"], "top", frozen)
        run.assert_not_called()

    def test_conversion_copies_all_dependencies_and_honors_synthesis_pragmas(self):
        (self.root / "include/common").mkdir(parents=True)
        (self.root / "include/common/defs.svh").write_text("`define WIDTH 8\n")
        original = (
            self.root / "top.sv"
        ).read_text() + "// synthesis translate_off\nunsupported_simulation();\n// synthesis translate_on\n"
        (self.root / "top.sv").write_text(original)
        frozen = freeze_frontend(self.root, self.spec, self.root / "frontend")
        commands = []

        def execute(command, work, name, **kwargs):
            commands.append((name, command))
            (work / kwargs["expected"][0]).write_text("module top; endmodule\n")

        with (
            patch("dv_platform.enterprise.rtl_frontend.run_native", side_effect=execute),
            patch("dv_platform.enterprise.rtl.run_native", side_effect=execute),
            patch("dv_platform.enterprise.rtl.shutil.which", side_effect=lambda name: "/tools/" + name),
        ):
            result = lower_rtl_sources(
                self.root,
                ["types.sv", "top.sv", "include/common/defs.svh"],
                "top",
                self.root / "lowered",
                frontend=frozen,
                memory_mb=8192,
            )
        self.assertTrue(result.is_file())
        self.assertEqual([name for name, _ in commands], ["sv2v", "synthesize"])
        self.assertTrue(all("--as=8589934592" in command for _, command in commands))
        self.assertIn("-Iinputs/include", commands[0][1])
        self.assertIn("-DSYNTHESIS", commands[0][1])
        self.assertEqual((self.root / "top.sv").read_text(), original)
        self.assertNotIn("unsupported_simulation", (self.root / "lowered/inputs/top.sv").read_text())
        self.assertIn("converted.v", (self.root / "lowered/synthesize.ys").read_text())

    def test_noneditable_dependencies_cannot_be_changed(self):
        snapshot = self.root / "snapshot"
        record = snapshot_rtl(self.root, ["types.sv", "top.sv"], ["design.md"], snapshot)
        record["editable_sources"] = ["top.sv"]
        with self.assertRaisesRegex(ValueError, "declared source"):
            materialize_candidate(
                snapshot, record, [{"path": "types.sv", "before": "7:0", "after": "3:0"}], self.root / "bad"
            )

    @skipUnless(SV2V and shutil.which("yosys") and shutil.which("prlimit"), "native sv2v/Yosys unavailable")
    def test_native_package_conversion_and_source_proofs(self):
        shutil.copyfile(SV2V, self.root / "converter")
        self.spec["sha256"] = file_digest(self.root / "converter")
        frontend = freeze_frontend(self.root, self.spec, self.root / "frontend")
        snapshot = self.root / "snapshot"
        record = snapshot_rtl(self.root, ["types.sv", "top.sv"], ["design.md"], snapshot)
        for label, after in (("equivalent", "a"), ("rejected", "~a")):
            with self.subTest(label=label):
                result = prove_rtl_candidate(
                    snapshot,
                    record,
                    [{"path": "top.sv", "before": "a & a", "after": after}],
                    "top",
                    self.root / label,
                    frontend=frontend,
                )
                self.assertEqual(result["status"], label, result.get("error"))
