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
class GeneratedMemoryDepthPipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "ignored byte enables",
        2: "wrong read-during-write behavior",
        3: "fixed-priority starvation",
        4: "incorrect initialization",
        5: "missing parity detection",
        6: "non-exclusive arbitration grants",
        7: "discarded port-1 write",
        8: "misaddressed read",
    }

    def test_generated_cocotb_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenarios = [item for item in plan.scenarios if item.kind == "memory_bounded_sram"]
                self.assertEqual(len(scenarios), 1)
                self.assertTrue(scenarios[0].executable)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                generated = config.output_dir / "simulation" / "cocotb" / "modules" / "memory_bounded_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "memory_bounded_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "memory_bounded_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    executable = {check.check_id for check in plan.check_details if check.executable}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated memory collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_formal_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "memory_bounded_qualified"
                harness = (generated / "formal_memory_bounded_qualified.sv").read_text(encoding="utf-8")
                self.assertIn("a_memory_1_exclusive_grant", harness)
                self.assertIn("a_memory_1_parity_detect", harness)
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "formal", "--module", "memory_bounded_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "memory_bounded_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    executable = {check.check_id for check in plan.check_details if check.executable}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated formal memory collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        return VerificationDepthPolicy(
            "memory",
            "memory_bounded_qualified",
            "storage",
            (
                ("profile", "bounded_sram"),
                ("clock", "clk"),
                ("reset", "rst_n"),
                ("read_during_write", "write_first"),
                ("initialization", "zero"),
                ("read_enable", "read_enable"),
                ("read_address", "read_address"),
                ("read_data", "read_data"),
                ("port0_request", "port0_request"),
                ("port0_write_enable", "port0_write_enable"),
                ("port0_address", "port0_address"),
                ("port0_write_data", "port0_write_data"),
                ("port0_byte_enable", "port0_byte_enable"),
                ("port0_grant", "port0_grant"),
                ("port1_request", "port1_request"),
                ("port1_write_enable", "port1_write_enable"),
                ("port1_address", "port1_address"),
                ("port1_write_data", "port1_write_data"),
                ("port1_byte_enable", "port1_byte_enable"),
                ("port1_grant", "port1_grant"),
                ("arbitration", "round_robin"),
                ("protection", "parity"),
                ("error_signal", "parity_error"),
                ("inject_error", "inject_error"),
                ("max_latency_cycles", "4"),
            ),
        )

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "memory_bounded_qualified.sv", rtl / "memory_bounded_qualified.sv")
        (rtl / "files.f").write_text("memory_bounded_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("memory_bounded_qualified",),
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


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GeneratedSecdedMemoryDepthPipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "missing single-error correction indication",
        2: "uncorrected single-error data",
        3: "missing double-error detection",
        4: "missing scrub completion",
        5: "false clean-read error indication",
    }

    def test_generated_cocotb_passes_good_dut_and_kills_secded_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "memory_bounded_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "memory_bounded_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                else:
                    self.assertNotEqual(result, 0, f"generated SECDED collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_formal_passes_good_dut_and_kills_secded_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                harness = (
                    config.output_dir
                    / "formal"
                    / "modules"
                    / "memory_bounded_qualified"
                    / "formal_memory_bounded_qualified.sv"
                ).read_text(encoding="utf-8")
                self.assertIn("a_memory_1_secded_correct", harness)
                self.assertIn("a_memory_1_secded_double_detect", harness)
                self.assertIn("a_memory_1_secded_scrub", harness)
                result = self._cli(root, "run", "--target", "formal", "--module", "memory_bounded_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "memory_bounded_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                else:
                    self.assertNotEqual(result, 0, f"generated formal SECDED collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        base = dict(GeneratedMemoryDepthPipelineTests._policy().parameters)
        base.pop("error_signal")
        base.pop("inject_error")
        base.update(
            {
                "protection": "secded",
                "corrected_error_signal": "corrected_error",
                "uncorrectable_error_signal": "uncorrectable_error",
                "inject_single_error": "inject_single_error",
                "inject_double_error": "inject_double_error",
                "scrub_enable": "scrub_enable",
                "scrub_done": "scrub_done",
            }
        )
        return VerificationDepthPolicy("memory", "memory_bounded_qualified", "storage", tuple(sorted(base.items())))

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "memory_secded_qualified.sv", rtl / "memory_bounded_qualified.sv")
        (rtl / "files.f").write_text("memory_bounded_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("memory_bounded_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=(cls._policy(),),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config

    _cli = staticmethod(GeneratedMemoryDepthPipelineTests._cli)


if __name__ == "__main__":
    unittest.main()
