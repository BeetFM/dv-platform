import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.generators.systemverilog import SystemVerilogGenerator

FIXTURES = Path(__file__).parent / "fixtures" / "mutations"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GeneratedAXI4LitePipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "coupled AW/W acceptance",
        2: "lost BVALID",
        3: "unstable BRESP",
        4: "dropped RVALID",
        5: "unstable RDATA/RRESP",
        6: "ignored WSTRB",
        7: "incorrect error responses",
        8: "second outstanding request",
        9: "early BVALID",
        10: "second outstanding read request",
    }

    def test_generated_axi4_lite_pipeline_passes_good_dut_and_is_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
            plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            executable = {check.check_id for check in plan.check_details if check.executable}
            scenario = next(item for item in plan.scenarios if item.kind == "axi4_lite_single_outstanding")
            self.assertTrue(scenario.executable, repr(scenario))
            self.assertTrue(executable)
            sva = "\n".join(artifact.content for artifact in SystemVerilogGenerator().generate(plan))
            self.assertIn("dv_profile_axi4_lite_1_0_exercise", sva)
            self.assertIn("while ((awready !== 1'b1)", sva)
            self.assertIn("held_payload = {bresp}", sva)
            self.assertIn("held_payload = {rdata, rresp}", sva)

            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            generated = config.output_dir / "simulation" / "cocotb" / "modules" / "axi4_lite_qualified_slave"
            first = self._snapshot(generated)
            source = (generated / "test_axi4_lite_qualified_slave.py").read_text(encoding="utf-8")
            self.assertIn("class AXI4LiteDriver", source)
            self.assertIn("class AXI4LiteMonitor", source)
            self.assertIn("class AXI4LiteReferenceModel", source)
            self.assertIn("independent-channel scoreboard mismatch", source)
            self.assertNotIn("Executable AXI4-Lite transfer probe", source)
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(self._snapshot(generated), first)

            self.assertEqual(self._cli(root, "run", "--target", "cocotb", "--module", "axi4_lite_qualified_slave"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
            summary = json.loads(
                (
                    config.work_dir / "runs" / "simulation" / "cocotb" / "axi4_lite_qualified_slave" / "summary.json"
                ).read_text(encoding="utf-8")
            )
            outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
            self.assertEqual(set(outcomes), executable)
            self.assertEqual(set(outcomes.values()), {"pass"})

    def test_generated_axi4_lite_pipeline_kills_required_mutants(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                self.assertNotEqual(
                    self._cli(root, "run", "--target", "cocotb", "--module", "axi4_lite_qualified_slave"),
                    0,
                    f"generated AXI4-Lite collateral did not kill {label}",
                )
                self.assertNotEqual(self._cli(root, "coverage", "--from-runs"), 0)
                self.assertNotEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                summary = json.loads(
                    (
                        config.work_dir
                        / "runs"
                        / "simulation"
                        / "cocotb"
                        / "axi4_lite_qualified_slave"
                        / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_axi4_lite_formal_passes_good_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                executable = {check.check_id for check in plan.check_details if check.executable}
                self.assertTrue(executable)
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "axi4_lite_qualified_slave"
                harness = (generated / "formal_axi4_lite_qualified_slave.sv").read_text(encoding="utf-8")
                self.assertIn("a_axi_b_after_aw_w", harness)
                self.assertIn("a_axi_stable_b", harness)
                self.assertIn("a_axi_stable_r", harness)
                self.assertIn("a_axi_CONTROL_read_scoreboard", harness)
                self.assertIn("c_axi_aw_before_w", harness)
                self.assertIn("dv_axi_read_expected", harness)
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "formal", "--module", "axi4_lite_qualified_slave")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "axi4_lite_qualified_slave" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                else:
                    self.assertNotEqual(result, 0, f"generated AXI4-Lite formal collateral did not kill {label}")
                    self.assertNotEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertNotEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--repo-root", str(root), *arguments])
        if result != 0 and arguments[0] in {"analyze-rtl", "plan", "generate"}:
            raise AssertionError(output.getvalue())
        return result

    @staticmethod
    def _snapshot(directory: Path) -> dict[str, bytes]:
        return {
            path.relative_to(directory).as_posix(): path.read_bytes()
            for path in sorted(directory.rglob("*"))
            if path.is_file()
        }

    @staticmethod
    def _configure(root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "axi4_lite_qualified_slave.sv", rtl / "axi4_lite_qualified_slave.sv")
        shutil.copy2(FIXTURES / "axi4_lite_registers.json", root / "axi4_lite_registers.json")
        (rtl / "files.f").write_text("axi4_lite_qualified_slave.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("axi4_lite_qualified_slave",),
            parameter_overrides=(f"MUTANT={mutant}",),
            register_map_paths=(root / "axi4_lite_registers.json",),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config


if __name__ == "__main__":
    unittest.main()
