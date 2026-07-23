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
from dv_platform.core.models import FormalToolConfig
from tests.formal.test_formal_depth import formal_policy
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "mutations" / "formal"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
    "requires Verilator, SymbiYosys, Yosys, and Z3",
)
class GeneratedFormalDepthPipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "missing response",
        2: "late response",
        3: "broken induction invariant",
        4: "non-causal response",
    }

    def test_generated_formal_contract_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenarios = [item for item in plan.scenarios if item.kind == "formal_bounded_response"]
                self.assertEqual(len(scenarios), 1)
                self.assertTrue(scenarios[0].executable)
                self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                generated = config.output_dir / "formal" / "modules" / "formal_contract_qualified"
                harness = (generated / "formal_formal_contract_qualified.sv").read_text(encoding="utf-8")
                self.assertIn("a_formal_contract_1_bounded_liveness", harness)
                self.assertIn("a_formal_contract_1_induction_state", harness)
                self.assertIn("c_formal_contract_1_assumption_witness", harness)
                sby = (generated / "formal_contract_qualified.sby").read_text(encoding="utf-8")
                self.assertIn("prove: mode prove", sby)
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "formal", "--module", "formal_contract_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "formal_contract_qualified" / "summary.json").read_text(
                        encoding="utf-8"
                    )
                )
                if mutant == 0:
                    self.assertEqual(result, 0, json.dumps(summary, indent=2))
                    self.assertEqual(summary["formal_status"], "pass")
                    self.assertEqual(summary["proof_method"], "k-induction")
                    outcomes = {item["check_id"]: item["outcome"] for item in summary["validation_result"]["checks"]}
                    executable = {check.check_id for check in plan.check_details if check.executable}
                    self.assertEqual(set(outcomes), executable)
                    self.assertEqual(set(outcomes.values()), {"pass"})
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated formal contract did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "formal_contract_qualified.sv", rtl / "formal_contract_qualified.sv")
        (rtl / "files.f").write_text("formal_contract_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("formal_contract_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=(formal_policy(),),
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
