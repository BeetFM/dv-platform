import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import SimulatorConfig, VerificationTarget
from tests.support.paths import FIXTURES_ROOT

FIXTURE = FIXTURES_ROOT / "rtl" / "simple_counter.sv"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class ParameterSweepPipelineTests(unittest.TestCase):
    def test_full_pipeline_closes_and_reports_every_sweep_cross_point(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "rtl"
            rtl.mkdir()
            shutil.copy2(FIXTURE, rtl / "simple_counter.sv")
            (rtl / "files.f").write_text("simple_counter.sv\n", encoding="utf-8")
            config = replace(
                default_config(root),
                rtl_filelists=(rtl / "files.f",),
                top_modules=("simple_counter",),
                parameter_sweeps=(("WIDTH=4",), ("WIDTH=9",)),
                simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            )
            write_config(config, root / "dv-platform.toml")

            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(self._cli(root, "run", "--target", "cocotb", "--all"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)

            summary = json.loads((config.work_dir / "coverage" / "summary.json").read_text(encoding="utf-8"))
            sweeps = summary["parameter_sweeps"]
            self.assertTrue(sweeps["passed"])
            self.assertEqual(sweeps["configured_points"], 2)
            self.assertEqual(len(sweeps["groups"]), 1)
            self.assertEqual(
                {point["parameters"]["WIDTH"] for point in sweeps["groups"][0]["points"]},
                {"32'h4", "32'h9"},
            )
            self.assertTrue(all(point["passed"] for point in sweeps["groups"][0]["cross_points"]))

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        output = StringIO()
        with redirect_stdout(output):
            result = main(["--repo-root", str(root), *arguments])
        if result != 0:
            summary = root / ".dv-platform" / "coverage" / "summary.json"
            detail = summary.read_text(encoding="utf-8") if summary.is_file() else ""
            raise AssertionError(output.getvalue() + detail)
        return result


if __name__ == "__main__":
    unittest.main()
