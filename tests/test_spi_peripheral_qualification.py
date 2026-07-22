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
class SPIPeripheralQualificationTests(unittest.TestCase):
    MUTANTS = {
        1: "wrong CPOL",
        2: "wrong CPHA edge",
        3: "chip select not asserted",
        4: "reversed transmit order",
        5: "ignored LSB-first mode",
        6: "corrupted receive order",
        7: "missing trailing edge",
        8: "wrong clock divider",
        9: "premature done",
    }

    def test_generated_spi_pipeline_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                self.assertTrue(next(item for item in plan.scenarios if item.kind == "spi_bounded").executable)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "spi_bounded_qualified")
                if mutant == 0:
                    log = (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "spi_bounded_qualified" / "stdout.log"
                    ).read_text(encoding="utf-8", errors="replace")
                    self.assertEqual(result, 0, log)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated SPI collateral did not kill {label}")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_spi_formal_properties_pass_good_dut(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            source = (
                config.output_dir / "formal" / "modules" / "spi_bounded_qualified" / "formal_spi_bounded_qualified.sv"
            ).read_text(encoding="utf-8")
            self.assertIn("a_spi_", source)
            self.assertEqual(self._cli(root, "run", "--target", "formal", "--module", "spi_bounded_qualified"), 0)

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        names = (
            "clock",
            "reset",
            "start",
            "tx_data",
            "rx_data",
            "busy",
            "done",
            "sclk",
            "mosi",
            "miso",
            "cs_n",
            "mode",
            "lsb_first",
        )
        parameters = {
            "profile": "bounded_master",
            "word_bits": "8",
            "clock_divider": "2",
            "max_transfer_cycles": "256",
            **{name: name for name in names},
        }
        return VerificationDepthPolicy("spi", "spi_bounded_qualified", "controller", tuple(sorted(parameters.items())))

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "spi_bounded_qualified.sv", rtl / "spi_bounded_qualified.sv")
        (rtl / "files.f").write_text("spi_bounded_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("spi_bounded_qualified",),
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


if __name__ == "__main__":
    unittest.main()
