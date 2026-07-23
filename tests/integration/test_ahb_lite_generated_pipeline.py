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

FIXTURES = Path(__file__).parent / "fixtures" / "mutations"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GeneratedAHBLitePipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "discarded write",
        2: "writable RO field",
        3: "broken W1C field",
        4: "missing HRESP",
        5: "dropped HREADYOUT",
        6: "incorrect reset value",
    }

    def test_generated_ahb_lite_pipeline_passes_good_dut_and_is_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
            plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            scenario = next(item for item in plan.scenarios if item.kind == "ahb_lite_single_beat")
            self.assertTrue(scenario.executable, repr(scenario))
            self.assertEqual(scenario.supported_targets, (VerificationTarget.COCOTB,))

            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            generated = config.output_dir / "simulation" / "cocotb" / "modules" / "ahb_lite_qualified_slave"
            first = self._snapshot(generated)
            source = (generated / "test_ahb_lite_qualified_slave.py").read_text(encoding="utf-8")
            self.assertIn("class AHBLiteDriver", source)
            self.assertIn("class AHBLiteMonitor", source)
            self.assertIn("class AHBLiteReferenceModel", source)
            self.assertNotIn("Executable AHB-Lite transfer probe", source)
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(self._snapshot(generated), first)

            self.assertEqual(self._cli(root, "run", "--target", "cocotb", "--module", "ahb_lite_qualified_slave"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
            summary = json.loads(
                (
                    config.work_dir / "runs" / "simulation" / "cocotb" / "ahb_lite_qualified_slave" / "summary.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(summary["validation_result"]["status"], "passed")

    def test_generated_ahb_lite_pipeline_kills_required_mutants(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                self.assertNotEqual(
                    self._cli(root, "run", "--target", "cocotb", "--module", "ahb_lite_qualified_slave"),
                    0,
                    f"generated AHB-Lite collateral did not kill {label}",
                )
                self.assertNotEqual(self._cli(root, "coverage", "--from-runs"), 0)
                self.assertNotEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "ahb_lite_qualified_slave" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_ahb_lite_formal_passes_good_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenario = next(item for item in plan.scenarios if item.kind == "ahb_lite_single_beat")
                self.assertTrue(scenario.executable, repr(scenario))
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "ahb_lite_qualified_slave"
                harness = (generated / "formal_ahb_lite_qualified_slave.sv").read_text(encoding="utf-8")
                self.assertIn("a_ahb_bounded_completion", harness)
                self.assertIn("a_ahb_CONTROL_read_scoreboard", harness)
                self.assertIn("c_ahb_error", harness)
                result = self._cli(root, "run", "--target", "formal", "--module", "ahb_lite_qualified_slave")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "ahb_lite_qualified_slave" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated AHB-Lite formal collateral did not kill {label}")
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
        shutil.copy2(FIXTURES / "ahb_lite_qualified_slave.sv", rtl / "ahb_lite_qualified_slave.sv")
        shutil.copy2(FIXTURES / "ahb_lite_registers.json", root / "ahb_lite_registers.json")
        (rtl / "files.f").write_text("ahb_lite_qualified_slave.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("ahb_lite_qualified_slave",),
            parameter_overrides=(f"MUTANT={mutant}",),
            register_map_paths=(root / "ahb_lite_registers.json",),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config


if __name__ == "__main__":
    unittest.main()
