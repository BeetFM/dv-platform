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
class GeneratedResetDomainPipelineTests(unittest.TestCase):
    MUTANTS = {
        1: "broken source async assertion",
        2: "early source release",
        3: "bypassed reset dependency",
        4: "corrupted RDC synchronizer",
        5: "early destination release",
        6: "broken destination async assertion",
    }

    def test_generated_cocotb_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenarios = [item for item in plan.scenarios if item.kind == "reset_domain_sequence"]
                self.assertEqual(len(scenarios), 2)
                self.assertTrue(all(item.executable for item in scenarios))
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                generated = config.output_dir / "simulation" / "cocotb" / "modules" / "reset_domains_qualified"
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "reset_domains_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "reset_domains_qualified" / "summary.json"
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
                    self.assertNotEqual(result, 0, f"generated reset collateral did not kill {label}")
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
                generated = config.output_dir / "formal" / "modules" / "reset_domains_qualified"
                harness = (generated / "formal_reset_domains_qualified.sv").read_text(encoding="utf-8")
                self.assertIn("a_reset_domain_1_async_assert", harness)
                self.assertIn("a_reset_domain_2_ordered_hold", harness)
                if mutant == 0:
                    first = self._snapshot(generated)
                    self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
                    self.assertEqual(self._snapshot(generated), first)
                result = self._cli(root, "run", "--target", "formal", "--module", "reset_domains_qualified")
                summary = json.loads(
                    (config.work_dir / "runs" / "formal" / "reset_domains_qualified" / "summary.json").read_text(
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
                    self.assertNotEqual(result, 0, f"generated formal reset collateral did not kill {label}")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _policies() -> tuple[VerificationDepthPolicy, ...]:
        return (
            VerificationDepthPolicy(
                "reset",
                "reset_domains_qualified",
                "src_rst_n",
                (
                    ("clock", "src_clk"),
                    ("release_cycles", "2"),
                    ("asynchronous_assertion", "true"),
                    ("ready_signal", "src_ready"),
                    ("min_assert_cycles", "2"),
                    ("recovery_cycles", "1"),
                    ("removal_cycles", "1"),
                ),
            ),
            VerificationDepthPolicy(
                "reset",
                "reset_domains_qualified",
                "dst_rst_n",
                (
                    ("clock", "dst_clk"),
                    ("release_cycles", "2"),
                    ("asynchronous_assertion", "true"),
                    ("ready_signal", "dst_ready"),
                    ("depends_on_reset", "src_rst_n"),
                    ("depends_on_ready", "src_ready"),
                    ("dependency_sync_signal", "dependency_sync"),
                    ("min_assert_cycles", "2"),
                    ("recovery_cycles", "1"),
                    ("removal_cycles", "1"),
                ),
            ),
        )

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "reset_domains_qualified.sv", rtl / "reset_domains_qualified.sv")
        (rtl / "files.f").write_text("reset_domains_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("reset_domains_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            depth_policies=cls._policies(),
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
