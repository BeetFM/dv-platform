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
class UARTPeripheralQualificationTests(unittest.TestCase):
    MUTANTS = {
        1: "wrong baud divisor",
        2: "reversed TX data",
        3: "wrong TX parity",
        4: "missing second stop bit",
        5: "TX idle low",
        6: "reversed RX data",
        7: "ignored parity error",
        8: "ignored framing error",
        9: "ignored break",
        10: "ignored overflow",
    }

    def test_generated_uart_pipeline_passes_good_dut_and_is_reproducible(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
            plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            scenario = next(item for item in plan.scenarios if item.kind == "uart_bounded")
            self.assertTrue(scenario.executable, repr(scenario))
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            generated = config.output_dir / "simulation" / "cocotb" / "modules" / "uart_bounded_qualified"
            first = self._snapshot(generated)
            source = (generated / "test_uart_bounded_qualified.py").read_text(encoding="utf-8")
            self.assertIn("Qualify bounded UART TX/RX timing", source)
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(first, self._snapshot(generated))
            self.assertEqual(self._cli(root, "run", "--target", "cocotb", "--module", "uart_bounded_qualified"), 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
            summary = json.loads(
                (
                    config.work_dir / "runs" / "simulation" / "cocotb" / "uart_bounded_qualified" / "summary.json"
                ).read_text(encoding="utf-8")
            )
            self.assertEqual(summary["validation_result"]["status"], "passed")

    def test_generated_uart_pipeline_kills_mutants(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                self.assertNotEqual(
                    self._cli(root, "run", "--target", "cocotb", "--module", "uart_bounded_qualified"),
                    0,
                    f"generated UART collateral did not kill {label}",
                )

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_uart_formal_properties_pass_good_dut(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            generated = config.output_dir / "formal" / "modules" / "uart_bounded_qualified"
            source = (generated / "formal_uart_bounded_qualified.sv").read_text(encoding="utf-8")
            self.assertIn("a_uart_", source)
            self.assertEqual(self._cli(root, "run", "--target", "formal", "--module", "uart_bounded_qualified"), 0)

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        names = (
            "clock",
            "reset",
            "tx_start",
            "tx_data",
            "tx",
            "tx_busy",
            "rx",
            "rx_data",
            "rx_valid",
            "parity_mode",
            "stop_bits",
            "parity_error",
            "framing_error",
            "break_detect",
            "overflow",
            "rx_clear",
        )
        parameters = {
            "profile": "bounded_controller",
            "data_bits": "8",
            "clocks_per_bit": "4",
            "max_frame_cycles": "128",
            **{name: name for name in names},
        }
        return VerificationDepthPolicy(
            "uart",
            "uart_bounded_qualified",
            "controller",
            tuple(sorted(parameters.items())),
        )

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "uart_bounded_qualified.sv", rtl / "uart_bounded_qualified.sv")
        (rtl / "files.f").write_text("uart_bounded_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("uart_bounded_qualified",),
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
        if result != 0 and (
            arguments[0] in {"analyze-rtl", "plan", "generate"} or (arguments[0] == "run" and "formal" in arguments)
        ):
            logs = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in sorted((root / ".dv-platform" / "runs" / "formal").rglob("*.log"))
            )
            raise AssertionError(output.getvalue() + logs)
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
