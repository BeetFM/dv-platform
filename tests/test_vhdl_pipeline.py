import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.analysis.rtl import read_normalized_rtl_facts
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import SimulatorConfig, VerificationTarget

FIXTURE = Path(__file__).parent / "fixtures" / "rtl" / "parameterized_counter.vhd"
NATIVE_FIXTURE = Path(__file__).parent / "fixtures" / "rtl" / "native_reset_register.vhd"


class VHDLPipelineTests(unittest.TestCase):
    def test_observable_reset_generates_typed_native_result_contract(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(NATIVE_FIXTURE, root / NATIVE_FIXTURE.name)
            config = replace(default_config(root), top_modules=("native_reset_register",))
            write_config(config, root / "dv-platform.toml")

            self._cli(root, "analyze-rtl")
            self._cli(root, "plan", "--target", "vhdl")
            plans = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")
            reset = next(scenario for scenario in plans[0].scenarios if scenario.kind == "reset_sequence")
            support = next(item for item in reset.target_states if item.target == VerificationTarget.VHDL)
            self.assertEqual(str(support.state), "executable")

            self._cli(root, "generate", "--target", "vhdl")
            testbench = (
                config.output_dir
                / "simulation"
                / "vhdl"
                / "modules"
                / "native_reset_register"
                / "tb_native_reset_register.vhd"
            )
            content = testbench.read_text(encoding="utf-8")
            self.assertIn("if data_o /= (data_o'range => '0') then", content)
            self.assertIn('DV_PLATFORM_RESULT_V1 {""trace_id""', content)

    @unittest.skipUnless(shutil.which("ghdl"), "requires GHDL")
    def test_generated_vhdl_executes_with_normalized_per_check_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(NATIVE_FIXTURE, root / NATIVE_FIXTURE.name)
            config = replace(
                default_config(root),
                top_modules=("native_reset_register",),
                simulators=(SimulatorConfig(VerificationTarget.VHDL, "ghdl", "ghdl"),),
            )
            write_config(config, root / "dv-platform.toml")

            for command in ("analyze-rtl", "plan", "generate", "run"):
                arguments = (
                    (command, "--target", "vhdl", "--module", "native_reset_register")
                    if command == "run"
                    else (command, "--target", "vhdl")
                    if command != "analyze-rtl"
                    else (command,)
                )
                self._cli(root, *arguments)
            summary = json.loads(
                (config.work_dir / "runs" / "simulation" / "vhdl" / "native_reset_register" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["results_parse_status"], "parsed")
            self.assertEqual(summary["validation_result"]["status"], "passed")
            self.assertEqual(summary["verification_coverage"]["passed"], 1)
            self.assertEqual(summary["tool_qualification"]["tool"], "ghdl")
            self.assertEqual(summary["tool_qualification"]["status"], "supported")
            self.assertIsNotNone(summary["tool_qualification"]["detected"])
            self._cli(root, "coverage", "--from-runs")
            self._cli(root, "status", "--policy", "ci")

    def test_vhdl_only_generic_sweep_analyzes_plans_and_generates_deterministically(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "rtl"
            rtl.mkdir()
            shutil.copy2(FIXTURE, rtl / FIXTURE.name)
            (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
            config = replace(
                default_config(root),
                rtl_filelists=(rtl / "files.f",),
                top_modules=("parameterized_counter",),
                parameter_sweeps=(("WIDTH=5",), ("WIDTH=9",)),
                verilator_executable="tool-that-must-not-be-invoked-for-vhdl",
            )
            write_config(config, root / "dv-platform.toml")

            output = self._cli(root, "analyze-rtl")
            self.assertIn("normalization_frontend=vhdl-source-normalizer/1", output)
            modules = read_normalized_rtl_facts(config)
            self.assertEqual(len(modules), 2)
            self.assertEqual({module.port_details[-1].width for module in modules}, {5, 9})
            self.assertEqual({module.design_unit_kind for module in modules}, {"entity"})
            payload = json.loads((config.work_dir / "rtl-facts" / "modules.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["normalization_frontends"], ["vhdl-source-normalizer/1"])
            self.assertIsNone(payload["verilator_version"])

            self._cli(root, "plan", "--target", "vhdl")
            plans = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")
            self.assertEqual(len(plans), 2)
            self.assertEqual({plan.design_unit for plan in plans}, {"parameterized_counter"})
            self.assertEqual({plan.elaborated_design_unit for plan in plans}, {"rtl"})
            self._cli(root, "generate", "--target", "vhdl")
            generated_root = config.output_dir / "simulation" / "vhdl" / "modules"
            first = self._snapshot(generated_root)
            self._cli(root, "generate", "--target", "vhdl")
            self.assertEqual(self._snapshot(generated_root), first)
            testbenches = sorted(generated_root.glob("*/tb_*.vhd"))
            self.assertEqual(len(testbenches), 2)
            self.assertTrue(all("__" not in path.name for path in testbenches))
            contents = [path.read_text(encoding="utf-8") for path in testbenches]
            self.assertTrue(all("dut: entity work.parameterized_counter" in content for content in contents))
            self.assertEqual(sum("WIDTH => 5" in content for content in contents), 1)
            self.assertEqual(sum("WIDTH => 9" in content for content in contents), 1)

    def test_mixed_language_analysis_fails_with_explicit_boundary(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(FIXTURE, root / FIXTURE.name)
            (root / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            config = replace(default_config(root), top_modules=("top",))
            write_config(config, root / "dv-platform.toml")

            result, output = self._cli_result(root, "analyze-rtl")
            self.assertEqual(result, 2)
            self.assertIn("Mixed Verilog/SystemVerilog and VHDL elaboration is not qualified", output)

    def test_required_semantic_crosscheck_fails_closed_for_vhdl(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(FIXTURE, root / FIXTURE.name)
            config = replace(
                default_config(root),
                top_modules=("parameterized_counter",),
                semantic_crosscheck="required",
            )
            write_config(config, root / "dv-platform.toml")

            result, output = self._cli_result(root, "analyze-rtl")
            self.assertEqual(result, 2)
            self.assertIn("qualified Slang cross-check does not support VHDL", output)

    def test_vhdl_cache_preserves_frontend_and_report_only_crosscheck_status(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copy2(FIXTURE, root / FIXTURE.name)
            config = replace(
                default_config(root),
                top_modules=("parameterized_counter",),
                semantic_crosscheck="report",
            )
            write_config(config, root / "dv-platform.toml")

            self._cli(root, "analyze-rtl")
            cached = json.loads(self._cli(root, "--json", "analyze-rtl"))["data"]
            self.assertTrue(cached["cache_hit"])
            self.assertEqual(cached["normalization_frontends"], ["vhdl-source-normalizer/1"])
            self.assertEqual(cached["semantic_crosscheck_status"], "unsupported")

    @classmethod
    def _cli(cls, root: Path, *arguments: str) -> str:
        result, output = cls._cli_result(root, *arguments)
        if result != 0:
            raise AssertionError(output)
        return output

    @staticmethod
    def _cli_result(root: Path, *arguments: str) -> tuple[int, str]:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--repo-root", str(root), *arguments])
        return result, output.getvalue()

    @staticmethod
    def _snapshot(directory: Path) -> dict[str, bytes]:
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        }


if __name__ == "__main__":
    unittest.main()
