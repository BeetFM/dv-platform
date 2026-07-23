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

FIXTURE = FIXTURES_ROOT / "mutations" / "protocol" / "ready_valid_qualified.sv"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class ReadyValidQualificationTests(unittest.TestCase):
    def test_good_dut_closes_and_four_mutants_fail(self) -> None:
        for mutant in range(5):
            with self.subTest(mutant=mutant), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "cocotb"),
                    ("generate", "--target", "cocotb"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "ready_valid_qualified")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "ready_valid_qualified" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                if mutant == 0:
                    self.assertEqual(result, 0)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    self.assertTrue(summary["verification_coverage"]["closure_complete"])
                else:
                    self.assertNotEqual(result, 0, f"ready/valid mutant {mutant} survived")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    @staticmethod
    def _configure(root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURE, rtl / FIXTURE.name)
        (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("ready_valid_qualified",),
            parameter_overrides=(f"MUTANT={mutant}",),
            simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
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


if __name__ == "__main__":
    unittest.main()
