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
from dv_platform.core.models import (
    FormalToolConfig,
    SimulatorConfig,
    VerificationDepthPolicy,
    VerificationTarget,
)
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "mutations" / "cdc"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GeneratedCDCSchemePipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "stuck toggle",
        2: "dropped pulse",
        3: "dropped request",
        4: "dropped acknowledgement",
        5: "non-Gray synchronized counter",
        6: "corrupted coherent payload",
    }

    def test_generated_cocotb_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                executable = {check.check_id for check in plan.check_details if check.executable}
                scenarios = {item.kind: item for item in plan.scenarios if item.kind.startswith("cdc_")}
                self.assertEqual(
                    set(scenarios),
                    {"cdc_pulse", "cdc_toggle", "cdc_multi_bit_handshake", "cdc_gray"},
                )
                self.assertTrue(all(item.executable for item in scenarios.values()))
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                generated = config.output_dir / "simulation" / "cocotb" / "modules" / "cdc_schemes_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "cdc_schemes_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "cdc_schemes_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated CDC collateral did not kill {label}")
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
                self.assertTrue(all(item.executable for item in plan.scenarios if item.kind.startswith("cdc_")))
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "cdc_schemes_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                harness = (generated / "formal_cdc_schemes_qualified.sv").read_text(encoding="utf-8")
                self.assertIn("toggle_rise", harness)
                self.assertIn("pulse_observed", harness)
                self.assertIn("round_trip", harness)
                self.assertIn("gray_source_one_bit", harness)
                self.assertIn("payload_coherent_0", harness)
                result = self._cli(root, "run", "--target", "formal", "--module", "cdc_schemes_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "cdc_schemes_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated formal CDC collateral did not kill {label}")
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
        shutil.copy2(FIXTURES / "cdc_schemes_qualified.sv", rtl / "cdc_schemes_qualified.sv")
        (rtl / "files.f").write_text("cdc_schemes_qualified.sv\n", encoding="utf-8")
        policies = (
            VerificationDepthPolicy(
                "cdc",
                "cdc_schemes_qualified",
                "async_toggle",
                (
                    ("structure", "toggle"),
                    ("output_signal", "toggle_sync"),
                    ("max_latency_cycles", "5"),
                ),
            ),
            VerificationDepthPolicy(
                "cdc",
                "cdc_schemes_qualified",
                "async_pulse",
                (
                    ("structure", "pulse"),
                    ("output_signal", "pulse_sync"),
                    ("pulse_stretch_cycles", "2"),
                    ("max_latency_cycles", "5"),
                ),
            ),
            VerificationDepthPolicy(
                "cdc",
                "cdc_schemes_qualified",
                "req_async",
                (
                    ("structure", "multi_bit_handshake"),
                    ("output_signal", "req_sync"),
                    ("ack_input_signal", "ack_async"),
                    ("ack_output_signal", "ack_sync"),
                    ("data_signals", "payload"),
                    ("observed_data_signals", "payload_observed"),
                    ("max_latency_cycles", "5"),
                ),
            ),
            VerificationDepthPolicy(
                "cdc",
                "cdc_schemes_qualified",
                "gray_async",
                (
                    ("structure", "gray"),
                    ("output_signal", "gray_sync"),
                    ("max_latency_cycles", "5"),
                    ("max_source_steps_per_destination", "1"),
                ),
            ),
        )
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("cdc_schemes_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=policies,
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config


if __name__ == "__main__":
    unittest.main()
