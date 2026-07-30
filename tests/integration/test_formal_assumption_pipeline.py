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
from dv_platform.core.models import FormalToolConfig, VerificationDepthPolicy
from tests.support.paths import FIXTURES_ROOT

FIXTURE = FIXTURES_ROOT / "mutations" / "formal" / "formal_assumption_qualified.sv"


@unittest.skipUnless(
    shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
    "requires SymbiYosys, Yosys, and Z3",
)
class GeneratedFormalAssumptionPipelineTests(unittest.TestCase):
    def test_real_sby_proves_typed_assumptions_and_kills_mutant(self) -> None:
        for mutant, label in ((0, "good DUT"), (1, "reset-output mutant")):
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenarios = [item for item in plan.scenarios if item.kind == "formal_assumption"]
                self.assertEqual(
                    {dict(item.stimulus[0].parameters)["signal"] for item in scenarios},
                    {"range_i", "stable_i"},
                )
                self.assertTrue(all(item.executable for item in scenarios))
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "formal_assumption_qualified"
                harness_path = generated / "formal_formal_assumption_qualified.sv"
                harness = harness_path.read_text(encoding="utf-8")
                self.assertIn("assume((range_i >= 0) && (range_i <= 9))", harness)
                self.assertIn("assume($stable(stable_i))", harness)
                self.assertIn("c_formal_assumption_1_completion", harness)
                self.assertIn("c_formal_assumption_2_completion", harness)
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "formal", "--module", "formal_assumption_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "formal_assumption_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    run_dir = config.work_dir / "runs" / "formal" / "formal_assumption_qualified"
                    self.assertTrue((run_dir / "formal_assumption_qualified_cover" / "PASS").is_file())
                    traces = tuple((run_dir / "formal_assumption_qualified_cover").glob("engine_*/trace*.vcd"))
                    self.assertTrue(traces, "formal assumption witnesses were not retained")
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, "generated formal collateral did not kill the reset-output mutant")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _configure(root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURE, rtl / FIXTURE.name)
        (rtl / "files.f").write_text(f"{FIXTURE.name}\n", encoding="utf-8")
        policies = (
            VerificationDepthPolicy(
                "formal",
                "formal_assumption_qualified",
                "response_contract",
                (
                    ("profile", "bounded_response"),
                    ("clock", "clk"),
                    ("reset", "rst_n"),
                    ("trigger_signal", "trigger"),
                    ("response_signal", "response"),
                    ("invariant_signal", "invariant"),
                    ("max_latency_cycles", "2"),
                    ("assume_trigger_pulse", "true"),
                    ("require_response_causality", "true"),
                ),
            ),
            VerificationDepthPolicy(
                "formal_assumption",
                "formal_assumption_qualified",
                "input_range",
                (
                    ("assumption", "range"),
                    ("signal", "range_i"),
                    ("clock", "clk"),
                    ("reset", "rst_n"),
                    ("reset_active", "low"),
                    ("bound_cycles", "5"),
                    ("minimum", "0"),
                    ("maximum", "9"),
                    ("engine", "sby"),
                ),
            ),
            VerificationDepthPolicy(
                "formal_assumption",
                "formal_assumption_qualified",
                "input_stability",
                (
                    ("assumption", "stability"),
                    ("signal", "stable_i"),
                    ("clock", "clk"),
                    ("reset", "rst_n"),
                    ("reset_active", "low"),
                    ("bound_cycles", "4"),
                    ("engine", "sby"),
                ),
            ),
        )
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("formal_assumption_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=policies,
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
