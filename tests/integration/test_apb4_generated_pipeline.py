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
class GeneratedAPB4PipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "discarded write",
        2: "ignored PSTRB",
        3: "writable RO field",
        4: "broken W1C field",
        5: "missing PSLVERR",
        6: "premature PREADY",
        7: "dropped PREADY",
        8: "unstable wait-state response",
        9: "incorrect reset value",
    }

    def test_generated_apb4_pipeline_passes_good_dut_and_is_byte_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)

            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
            plans = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")
            executable_checks = {check.check_id for check in plans[0].check_details if check.executable}
            self.assertTrue(executable_checks)
            self.assertTrue(
                all(scenario.executable for scenario in plans[0].scenarios if scenario.kind.startswith("apb4")),
                repr(plans[0].scenarios),
            )

            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            generated_dir = config.output_dir / "simulation" / "cocotb" / "modules" / "apb4_qualified_slave"
            first = self._snapshot(generated_dir)
            generated_test = (generated_dir / "test_apb4_qualified_slave.py").read_text(encoding="utf-8")
            self.assertIn("class APB4Driver", generated_test)
            self.assertIn("class APB4Monitor", generated_test)
            self.assertIn("class APB4RegisterReferenceModel", generated_test)
            self.assertIn("APB4 PSTRB/field-policy scoreboard mismatch", generated_test)
            self.assertNotIn("Executable APB4 transfer probe", generated_test)

            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(self._snapshot(generated_dir), first)
            self.assertEqual(self._cli(root, "run", "--target", "cocotb", "--module", "apb4_qualified_slave"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)

            summary = json.loads(
                (
                    config.work_dir / "runs" / "simulation" / "cocotb" / "apb4_qualified_slave" / "summary.json"
                ).read_text(encoding="utf-8")
            )
            validation = summary["validation_result"]
            self.assertEqual(validation["status"], "passed")
            outcomes = {item["check_id"]: item["outcome"] for item in validation["checks"]}
            self.assertEqual(set(outcomes), executable_checks)
            self.assertEqual(set(outcomes.values()), {"pass"})

    def test_generated_apb4_collateral_kills_every_required_mutant(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                self.assertNotEqual(
                    self._cli(root, "run", "--target", "cocotb", "--module", "apb4_qualified_slave"),
                    0,
                    f"generated APB4 collateral did not kill {label}",
                )
                self.assertNotEqual(self._cli(root, "coverage", "--from-runs"), 0)
                self.assertNotEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "apb4_qualified_slave" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_apb4_formal_sva_passes_good_dut_and_is_byte_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
            plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            executable_checks = {check.check_id for check in plan.check_details if check.executable}
            self.assertTrue(executable_checks)
            self.assertTrue(all(scenario.executable for scenario in plan.scenarios if scenario.kind.startswith("apb4")))

            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            generated_dir = config.output_dir / "formal" / "modules" / "apb4_qualified_slave"
            first = self._snapshot(generated_dir)
            harness = (generated_dir / "formal_apb4_qualified_slave.sv").read_text(encoding="utf-8")
            self.assertIn("a_apb_bounded_completion", harness)
            self.assertIn("a_apb_CONTROL_read_scoreboard", harness)
            self.assertIn("c_apb_error", harness)
            self.assertNotIn("assert property", harness)
            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            self.assertEqual(self._snapshot(generated_dir), first)

            self.assertEqual(self._cli(root, "run", "--target", "formal", "--module", "apb4_qualified_slave"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
            summary = json.loads(
                (config.work_dir / "runs" / "formal" / "apb4_qualified_slave" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["formal_status"], "pass")
            outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
            self.assertEqual(set(outcomes), executable_checks)
            self.assertEqual(set(outcomes.values()), {"pass"})

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_apb4_formal_sva_kills_every_required_mutant(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                self.assertNotEqual(
                    self._cli(root, "run", "--target", "formal", "--module", "apb4_qualified_slave"),
                    0,
                    f"generated APB4 formal/SVA collateral did not kill {label}",
                )
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "apb4_qualified_slave" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(summary["validation_result"]["status"], "failed")
                self.assertNotEqual(self._cli(root, "coverage", "--from-runs"), 0)
                self.assertNotEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)

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
        rtl_dir = root / "rtl"
        rtl_dir.mkdir()
        shutil.copy2(FIXTURES / "apb4_qualified_slave.sv", rtl_dir / "apb4_qualified_slave.sv")
        shutil.copy2(FIXTURES / "apb4_registers.json", root / "apb4_registers.json")
        (rtl_dir / "files.f").write_text("apb4_qualified_slave.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl_dir / "files.f",),
            top_modules=("apb4_qualified_slave",),
            parameter_overrides=(f"MUTANT={mutant}",),
            register_map_paths=(root / "apb4_registers.json",),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config


if __name__ == "__main__":
    unittest.main()
