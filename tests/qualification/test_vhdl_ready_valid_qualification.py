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
from dv_platform.core.models import SimulatorConfig, VerificationTarget
from tests.support.paths import FIXTURES_ROOT

FIXTURE = FIXTURES_ROOT / "mutations" / "protocol" / "vhdl_ready_valid_qualified.vhd"


@unittest.skipUnless(shutil.which("ghdl"), "requires GHDL")
class VHDLReadyValidQualificationTests(unittest.TestCase):
    MUTANTS = {
        1: "incorrect reset state",
        2: "refused input transfer",
        3: "corrupted output data",
        4: "dropped valid under backpressure",
    }

    def test_project_pipeline_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "vhdl"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                self.assertEqual(len(plan.protocols), 2)
                self.assertTrue(any(check.category == "protocol" and check.executable for check in plan.check_details))
                self.assertEqual(self._cli(root, "generate", "--target", "vhdl"), 0)
                result = self._cli(root, "run", "--target", "vhdl", "--module", "vhdl_ready_valid_qualified")
                if mutant:
                    self.assertNotEqual(result, 0, f"generated VHDL collateral did not kill {label}")
                    continue
                stdout = (
                    config.work_dir / "runs" / "simulation" / "vhdl" / "vhdl_ready_valid_qualified" / "stdout.log"
                ).read_text(encoding="utf-8", errors="replace")
                stderr = (
                    config.work_dir / "runs" / "simulation" / "vhdl" / "vhdl_ready_valid_qualified" / "stderr.log"
                ).read_text(encoding="utf-8", errors="replace")
                self.assertEqual(result, 0, stdout + stderr)
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "vhdl" / "vhdl_ready_valid_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(summary["validation_result"]["status"], "passed")
                self.assertGreaterEqual(summary["verification_coverage"]["passed"], 2)
                self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                self.assertEqual(self._cli(root, "status", "--policy", "ci"), 0)

    def test_generated_project_is_byte_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            for command in ("analyze-rtl", "plan", "generate"):
                args = (command, "--target", "vhdl") if command != "analyze-rtl" else (command,)
                self.assertEqual(self._cli(root, *args), 0)
            generated = config.output_dir / "simulation" / "vhdl" / "modules" / "vhdl_ready_valid_qualified"
            first = {path.name: path.read_bytes() for path in generated.iterdir() if path.is_file()}
            self.assertEqual(self._cli(root, "generate", "--target", "vhdl"), 0)
            self.assertEqual(first, {path.name: path.read_bytes() for path in generated.iterdir() if path.is_file()})

    @staticmethod
    def _configure(root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURE, rtl / FIXTURE.name)
        (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("vhdl_ready_valid_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            simulators=(SimulatorConfig(VerificationTarget.VHDL, "ghdl", "ghdl"),),
        )
        write_config(config, root / "dv-platform.toml")
        return config

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        with redirect_stdout(StringIO()):
            return main(["--repo-root", str(root), *arguments])


if __name__ == "__main__":
    unittest.main()
