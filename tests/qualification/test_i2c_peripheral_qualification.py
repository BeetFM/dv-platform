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
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "mutations" / "peripheral"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class I2CPeripheralQualificationTests(unittest.TestCase):
    MUTANTS = {
        1: "missing START",
        2: "missing STOP",
        3: "missing repeated START",
        4: "ignored NACK",
        5: "ignored clock stretch",
        6: "ignored arbitration loss",
        7: "corrupted serialized write data",
        8: "corrupted read data",
    }

    def test_generated_i2c_pipeline_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                self.assertTrue(next(item for item in plan.scenarios if item.kind == "i2c_bounded").executable)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "i2c_bounded_qualified")
                if mutant == 0:
                    log = (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "i2c_bounded_qualified" / "stdout.log"
                    ).read_text(encoding="utf-8", errors="replace")
                    self.assertEqual(result, 0, log)
                    self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated I2C collateral did not kill {label}")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_i2c_formal_properties_pass_good_dut(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            source = (
                config.output_dir / "formal" / "modules" / "i2c_bounded_qualified" / "formal_i2c_bounded_qualified.sv"
            ).read_text(encoding="utf-8")
            self.assertIn("a_i2c_", source)
            result = self._cli(root, "run", "--target", "formal", "--module", "i2c_bounded_qualified")
            logs = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in sorted((config.work_dir / "runs" / "formal" / "i2c_bounded_qualified").rglob("*.log"))
            )
            self.assertEqual(result, 0, logs)

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        names = (
            "clock",
            "reset",
            "start",
            "read",
            "repeated_start",
            "address",
            "write_data",
            "read_data",
            "read_valid",
            "busy",
            "done",
            "ack_error",
            "arbitration_lost",
            "sda_drive_low",
            "sda_in",
            "scl_drive_low",
            "scl_in",
        )
        parameters = {
            "profile": "bounded_7bit_master",
            "clock_divider": "2",
            "max_stretch_cycles": "8",
            "max_transfer_cycles": "512",
            **{name: name for name in names},
        }
        return VerificationDepthPolicy("i2c", "i2c_bounded_qualified", "controller", tuple(sorted(parameters.items())))

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "i2c_bounded_qualified.sv", rtl / "i2c_bounded_qualified.sv")
        (rtl / "files.f").write_text("i2c_bounded_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("i2c_bounded_qualified",),
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
