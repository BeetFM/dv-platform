import io
import os
import shutil
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.rtl import normalize_verilator_xml
from dv_platform.analysis.semantic_crosscheck import NormalizedFactCrossChecker, SlangAnalyzer
from dv_platform.cli import main
from tests.support.paths import FIXTURES_ROOT


class SlangIntegrationTests(unittest.TestCase):
    @staticmethod
    def _slang() -> str:
        slang = shutil.which("slang")
        if slang is None:
            if os.environ.get("DV_PLATFORM_QUALIFIED_SLANG_CI") == "1":
                raise AssertionError("Qualified Slang CI requires slang on PATH")
            raise unittest.SkipTest("Slang 11 is not available on PATH")
        return slang

    def test_qualified_verilator_5_slang_11_cli_pairing(self) -> None:
        required = os.environ.get("DV_PLATFORM_QUALIFIED_SLANG_CI") == "1"
        verilator = shutil.which("verilator")
        slang = shutil.which("slang")
        if verilator is None or slang is None:
            message = "Qualified Slang CI requires both verilator and slang on PATH"
            if required:
                self.fail(message)
            self.skipTest(message)

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            rtl = repo / "rtl"
            rtl.mkdir()
            (rtl / "top.sv").write_text("module top(input logic clk); endmodule\n", encoding="utf-8")
            (rtl / "files.f").write_text("top.sv\n", encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                init_exit = main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                        "--verilator-executable",
                        verilator,
                        "--slang-executable",
                        slang,
                        "--semantic-crosscheck",
                        "required",
                    ]
                )
            self.assertEqual(init_exit, 0)

            output = io.StringIO()
            with redirect_stdout(output):
                analyze_exit = main(["--repo-root", str(repo), "--strict", "analyze-rtl"])

            self.assertEqual(analyze_exit, 0, output.getvalue())
            self.assertIn("semantic_crosscheck_status=passed", output.getvalue())
            self.assertTrue((repo / ".dv-platform" / "semantic-crosscheck" / "result.json").is_file())

    def test_real_slang_11_semantic_fixture_matrix(self) -> None:
        slang = self._slang()
        fixture_root = FIXTURES_ROOT / "slang"
        cases = (
            ("expressions_control.sv", "expressions_control"),
            ("properties.sv", "properties"),
            ("types_interfaces.sv", "types_interfaces_top"),
            ("hierarchy_generate_memory.sv", "hierarchy_generate_memory"),
        )
        with TemporaryDirectory() as temp_dir:
            for filename, top in cases:
                result = SlangAnalyzer(slang).run(
                    (fixture_root / filename,),
                    Path(temp_dir) / top / "ast.json",
                    top_modules=(top,),
                )
                self.assertTrue(result.succeeded, result.error)
                self.assertEqual(result.unsupported_capabilities, (), result.capability_reasons)
                by_name = {module.original_name: module for module in result.modules}
                if top == "expressions_control":
                    module = by_name[top]
                    self.assertTrue(module.procedural_block_details[0].branches)
                    self.assertEqual(module.control_domains[0].reset, "rst_n")
                    self.assertTrue(module.control_domains[0].asynchronous_reset)
                    self.assertTrue(
                        any(item.reset == "rst_n" and not item.asynchronous_reset for item in module.control_domains)
                    )
                elif top == "properties":
                    module = by_name[top]
                    self.assertEqual(len(module.property_details), 4)
                    self.assertTrue(all(item.support_status == "normalized" for item in module.property_details))
                elif top == "types_interfaces_top":
                    module = by_name["types_interfaces"]
                    self.assertEqual({port.modport for port in module.port_details if port.modport}, {"source", "sink"})
                    self.assertIn("types_pkg", module.imports)
                    self.assertTrue(any(item.name == "payload_t" and item.width == 6 for item in module.type_details))
                    self.assertTrue(any(item.name == "packet_t" and item.width == 7 for item in module.type_details))
                    self.assertEqual(
                        {port.unpacked_dimensions for port in module.port_details if port.interface_name},
                        {("[0:1]",)},
                    )
                else:
                    module = by_name[top]
                    self.assertEqual({item.name for item in module.memories}, {"memory", "chain"})
                    self.assertEqual(
                        {item.name for item in module.instance_details},
                        {"g_chain[0].u_child", "g_chain[1].u_child"},
                    )
                    self.assertTrue(any(item.enable_signals == ("write_en",) for item in module.memory_accesses))

            disabled = SlangAnalyzer(slang).run(
                (fixture_root / "hierarchy_generate_memory.sv",),
                Path(temp_dir) / "hierarchy_disabled" / "ast.json",
                top_modules=("hierarchy_generate_memory",),
                parameter_overrides=("ENABLE_EXTRA=0",),
            )
            self.assertTrue(disabled.succeeded, disabled.error)
            disabled_top = next(item for item in disabled.modules if item.original_name == "hierarchy_generate_memory")
            extra = next(item for item in disabled_top.generate_scopes if item.name == "g_extra")
            self.assertFalse(extra.selected)
            self.assertEqual(extra.condition.name, "ENABLE_EXTRA")

    def test_real_cross_frontend_compatibility_matrix_fails_closed(self) -> None:
        slang = self._slang()
        verilator = shutil.which("verilator")
        if verilator is None:
            if os.environ.get("DV_PLATFORM_QUALIFIED_SLANG_CI") == "1":
                self.fail("Qualified Slang CI requires Verilator 5 on PATH")
            self.skipTest("Verilator 5 is not available on PATH")
        fixture_root = FIXTURES_ROOT / "slang"
        cases = (
            ("expressions_control.sv", "expressions_control", {"assignments", "expressions", "branches"}),
            ("types_interfaces.sv", "types_interfaces", {"assignments", "expressions"}),
            (
                "hierarchy_generate_memory.sv",
                "hierarchy_generate_memory",
                {"instances", "assignments", "expressions", "branches", "generate_scopes"},
            ),
            ("properties_supported.sv", "properties_supported", {"properties"}),
        )
        with TemporaryDirectory(prefix="dv platform semantic matrix ") as temp_dir:
            root = Path(temp_dir)
            for filename, top, expected_issue_fields in cases:
                verilator_dir = root / top / "verilator xml"
                verilator_dir.mkdir(parents=True)
                completed = subprocess.run(
                    (
                        verilator,
                        "--xml-only",
                        "--assert",
                        "-Wno-fatal",
                        "--Mdir",
                        str(verilator_dir),
                        "--top-module",
                        top if top != "types_interfaces" else "types_interfaces_top",
                        str(fixture_root / filename),
                    ),
                    check=False,
                    capture_output=True,
                    text=True,
                )
                self.assertEqual(completed.returncode, 0, completed.stderr)
                primary_modules = normalize_verilator_xml(tuple(verilator_dir.glob("*.xml")))
                reference = SlangAnalyzer(slang).run(
                    (fixture_root / filename,),
                    root / top / "slang ast" / "ast.json",
                    top_modules=(top if top != "types_interfaces" else "types_interfaces_top",),
                )
                self.assertTrue(reference.succeeded, reference.error)
                primary = next(item for item in primary_modules if item.original_name == top)
                secondary = next(item for item in reference.modules if item.original_name == top)
                result = NormalizedFactCrossChecker().compare((primary,), (secondary,))
                fields = {issue.field for issue in result.issues}
                self.assertTrue(expected_issue_fields <= fields, (top, fields))
                self.assertTrue(all(issue.primary_location or issue.reference_location for issue in result.issues))

            unsupported_dir = root / "unsupported temporal"
            unsupported_dir.mkdir()
            unsupported = subprocess.run(
                (
                    verilator,
                    "--xml-only",
                    "--assert",
                    "--Mdir",
                    str(unsupported_dir),
                    "--top-module",
                    "properties",
                    str(fixture_root / "properties.sv"),
                ),
                check=False,
                capture_output=True,
                text=True,
            )
            self.assertNotEqual(unsupported.returncode, 0)
            self.assertIn("Unsupported", unsupported.stderr)


if __name__ == "__main__":
    unittest.main()
