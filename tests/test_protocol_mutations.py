import os
import shutil
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

FIXTURES = Path(__file__).parent / "fixtures" / "mutations"


@unittest.skipUnless(
    shutil.which("iverilog") and shutil.which("make") and shutil.which("cocotb-config"), "requires Icarus and cocotb"
)
class OpenToolProtocolMutationTests(unittest.TestCase):
    def _simulate(self, source: str, top: str, module: str) -> subprocess.CompletedProcess[str]:
        makefiles = subprocess.run(
            ["cocotb-config", "--makefiles"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        with TemporaryDirectory() as temp_dir:
            environment = os.environ.copy()
            existing_pythonpath = environment.get("PYTHONPATH")
            environment["PYTHONPATH"] = str(FIXTURES) + (
                os.pathsep + existing_pythonpath if existing_pythonpath else ""
            )
            return subprocess.run(
                [
                    "make",
                    "-f",
                    str(Path(makefiles) / "Makefile.sim"),
                    "SIM=icarus",
                    "TOPLEVEL_LANG=verilog",
                    f"VERILOG_SOURCES={FIXTURES / source}",
                    f"TOPLEVEL={top}",
                    f"MODULE={module}",
                    "COCOTB_RESULTS_FILE=results.xml",
                ],
                cwd=temp_dir,
                env=environment,
                capture_output=True,
                text=True,
                timeout=30,
            )

    def test_apb4_scoreboard_passes_good_dut_and_kills_discarded_write_mutant(self) -> None:
        good = self._simulate("apb4_slave_good.sv", "apb4_slave", "cocotb_apb4_mutation")
        mutant = self._simulate("apb4_slave_broken_scoreboard.sv", "apb4_slave", "cocotb_apb4_mutation")

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(mutant.returncode, 0, mutant.stdout + mutant.stderr)
        self.assertIn("APB4 register scoreboard mismatch", mutant.stdout + mutant.stderr)

    def test_axi4_lite_backpressure_check_passes_good_dut_and_kills_bvalid_mutant(self) -> None:
        good = self._simulate("axi4_lite_slave_good.sv", "axi4_lite_slave", "cocotb_axi4_lite_mutation")
        mutant = self._simulate("axi4_lite_slave_broken_bvalid.sv", "axi4_lite_slave", "cocotb_axi4_lite_mutation")

        self.assertEqual(good.returncode, 0, good.stdout + good.stderr)
        self.assertNotEqual(mutant.returncode, 0, mutant.stdout + mutant.stderr)
        self.assertIn("BVALID dropped under backpressure", mutant.stdout + mutant.stderr)


if __name__ == "__main__":
    unittest.main()
