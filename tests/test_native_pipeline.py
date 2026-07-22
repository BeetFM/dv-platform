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
from dv_platform.core.models import ScenarioTargetState, SimulatorConfig, VerificationTarget

FIXTURE = Path(__file__).parent / "fixtures" / "rtl" / "native_reset_register.v"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("vvp"),
    "requires Verilator and Icarus",
)
class NativePipelineTests(unittest.TestCase):
    def test_generated_systemverilog_and_verilog_close_with_native_results(self) -> None:
        for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
            with self.subTest(target=target), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                simulator = SimulatorConfig(target, "icarus", "iverilog")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("native_reset_register",),
                    simulators=(simulator,),
                )
                write_config(config, root / "dv-platform.toml")

                self._cli(root, "analyze-rtl")
                self._cli(root, "plan", "--target", target.value)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                reset_scenarios = [item for item in plan.scenarios if item.kind == "reset_sequence"]
                self.assertEqual(len(reset_scenarios), 1)
                support = next(item for item in reset_scenarios[0].target_states if item.target == target)
                self.assertEqual(support.state, ScenarioTargetState.EXECUTABLE)
                self.assertTrue(reset_scenarios[0].executable)

                self._cli(root, "generate", "--target", target.value)
                generated = config.output_dir / "simulation" / target.value / "modules" / plan.module
                extension = "sv" if target == VerificationTarget.SYSTEMVERILOG else "v"
                bench = (generated / f"tb_{plan.module}.{extension}").read_text(encoding="utf-8")
                self.assertIn("DV_PLATFORM_RESULT_V1", bench)
                first = self._snapshot(generated)
                self._cli(root, "generate", "--target", target.value)
                self.assertEqual(self._snapshot(generated), first)

                self._cli(root, "run", "--target", target.value, "--module", plan.module)
                summary_path = config.work_dir / "runs" / "simulation" / target.value / plan.module / "summary.json"
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                self.assertEqual(summary["validation_result"]["status"], "passed")
                self.assertTrue(summary["verification_coverage"]["closure_complete"])
                self.assertEqual(summary["results_parse_status"], "parsed")
                self.assertEqual(summary["native_results"]["schema_version"], 1)
                self._cli(root, "coverage", "--from-runs")
                self._cli(root, "status", "--policy", "ci", "--no-require-tools")

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--repo-root", str(root), *arguments])
        if result != 0:
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
