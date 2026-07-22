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
from dv_platform.core.models import FormalToolConfig, SimulatorConfig, VerificationDepthPolicy, VerificationTarget

FIXTURES = Path(__file__).parent / "fixtures" / "mutations"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GeneratedAsyncFIFOPipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "misaddressed write",
        2: "ignored full",
        3: "incorrect empty",
        4: "binary pointer crossing",
        5: "corrupt Gray synchronizer",
        6: "misaddressed read",
        7: "broken pointer wrap",
    }

    def test_generated_cocotb_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenario = next(item for item in plan.scenarios if item.kind == "cdc_async_fifo")
                self.assertTrue(scenario.executable)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                generated = config.output_dir / "simulation" / "cocotb" / "modules" / "async_fifo_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "async_fifo_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "async_fifo_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    executable = {check.check_id for check in plan.check_details if check.executable}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated FIFO collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_formal_passes_good_dut_and_kills_structural_mutants(self) -> None:
        for mutant, label in {
            0: "good DUT",
            2: self.MUTANTS[2],
            3: self.MUTANTS[3],
            4: self.MUTANTS[4],
            5: self.MUTANTS[5],
            7: self.MUTANTS[7],
        }.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "async_fifo_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                harness = (generated / "formal_async_fifo_qualified.sv").read_text(encoding="utf-8")
                self.assertIn("a_async_fifo_1_full_equation", harness)
                self.assertIn("a_async_fifo_1_empty_equation", harness)
                result = self._cli(root, "run", "--target", "formal", "--module", "async_fifo_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "async_fifo_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    executable = {check.check_id for check in plan.check_details if check.executable}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated formal collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        return VerificationDepthPolicy(
            "cdc",
            "async_fifo_qualified",
            "storage",
            (
                ("structure", "async_fifo"),
                ("min_stages", "2"),
                ("max_latency_cycles", "40"),
                ("write_clock", "wclk"),
                ("write_reset", "wrst_n"),
                ("write_enable", "w_en"),
                ("write_data", "w_data"),
                ("write_binary_pointer", "w_ptr_bin"),
                ("write_gray_pointer", "w_ptr_gray"),
                ("write_gray_sync", "w_gray_sync"),
                ("full_signal", "full"),
                ("read_clock", "rclk"),
                ("read_reset", "rrst_n"),
                ("read_enable", "r_en"),
                ("read_data", "r_data"),
                ("read_binary_pointer", "r_ptr_bin"),
                ("read_gray_pointer", "r_ptr_gray"),
                ("read_gray_sync", "r_gray_sync"),
                ("empty_signal", "empty"),
            ),
        )

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "async_fifo_qualified.sv", rtl / "async_fifo_qualified.sv")
        (rtl / "files.f").write_text("async_fifo_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("async_fifo_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=(cls._policy(),),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config

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


if __name__ == "__main__":
    unittest.main()
