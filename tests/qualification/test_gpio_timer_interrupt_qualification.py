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
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "mutations" / "peripheral"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class GPIOTimerInterruptQualificationTests(unittest.TestCase):
    MUTANTS = {
        1: "inverted GPIO direction",
        2: "ignored GPIO write mask",
        3: "ignored GPIO set",
        4: "lost GPIO interrupt",
        5: "lost timer compare",
        6: "ignored watchdog feed",
        7: "lost watchdog reset",
        8: "broken PWM rollover",
        9: "wrong fixed priority",
        10: "lost interrupt valid",
    }

    def test_generated_subsystem_pipeline_passes_good_dut_and_kills_mutants(self) -> None:
        for mutant, label in {0: "good DUT", **self.MUTANTS}.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                config = self._configure(root, mutant)
                self.assertEqual(self._cli(root, "analyze-rtl"), 0)
                self.assertEqual(self._cli(root, "plan", "--target", "cocotb"), 0)
                plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
                scenario = next(item for item in plan.scenarios if item.kind == "gpio_timer_interrupt_bounded")
                self.assertTrue(scenario.executable)
                self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "gpio_timer_interrupt_qualified")
                if mutant == 0:
                    log = (
                        config.work_dir
                        / "runs"
                        / "simulation"
                        / "cocotb"
                        / "gpio_timer_interrupt_qualified"
                        / "stdout.log"
                    ).read_text(encoding="utf-8", errors="replace")
                    self.assertEqual(result, 0, log)
                    coverage_result = self._cli(root, "coverage", "--from-runs")
                    coverage = json.loads((config.work_dir / "coverage" / "summary.json").read_text(encoding="utf-8"))
                    statements = {check.check_id: check.statement for check in plan.check_details}
                    unmeasured = [
                        statements.get(item["check_id"], item["check_id"])
                        for item in coverage["plan_feedback"]["unmeasured_checks"]
                    ]
                    self.assertEqual(coverage_result, 0, repr(unmeasured))
                    self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)
                else:
                    self.assertNotEqual(result, 0, f"generated peripheral collateral did not kill {label}")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_generated_subsystem_formal_properties_pass_good_dut(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = self._configure(root, 0)
            self.assertEqual(self._cli(root, "analyze-rtl"), 0)
            self.assertEqual(self._cli(root, "plan", "--target", "formal"), 0)
            self.assertEqual(self._cli(root, "generate", "--target", "formal"), 0)
            source = (
                config.output_dir
                / "formal"
                / "modules"
                / "gpio_timer_interrupt_qualified"
                / "formal_gpio_timer_interrupt_qualified.sv"
            ).read_text(encoding="utf-8")
            self.assertIn("a_gpio_", source)
            self.assertIn("a_watchdog_", source)
            self.assertIn("a_interrupt_", source)
            result = self._cli(root, "run", "--target", "formal", "--module", "gpio_timer_interrupt_qualified")
            logs = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in sorted(
                    (config.work_dir / "runs" / "formal" / "gpio_timer_interrupt_qualified").rglob("*.log")
                )
            )
            diagnostic = "\n".join(
                line
                for line in logs.splitlines()
                if "Assert failed" in line or "Unreached cover" in line or "DONE (" in line
            )
            self.assertEqual(result, 0, diagnostic)

    @staticmethod
    def _policy() -> VerificationDepthPolicy:
        names = (
            "clock",
            "reset",
            "gpio_input",
            "gpio_output",
            "gpio_output_enable",
            "gpio_write",
            "gpio_write_data",
            "gpio_write_mask",
            "gpio_set",
            "gpio_clear",
            "gpio_direction",
            "gpio_rise_enable",
            "gpio_fall_enable",
            "gpio_level_enable",
            "gpio_irq_pending",
            "gpio_irq_clear",
            "timer_enable",
            "timer_prescaler",
            "timer_compare",
            "timer_periodic",
            "timer_count",
            "timer_irq",
            "timer_irq_clear",
            "watchdog_enable",
            "watchdog_feed",
            "watchdog_timeout",
            "watchdog_irq",
            "watchdog_reset",
            "pwm_enable",
            "pwm_period",
            "pwm_duty",
            "pwm_polarity",
            "pwm_output",
            "interrupt_sources",
            "interrupt_mask",
            "interrupt_clear",
            "interrupt_pending",
            "interrupt_ack",
            "interrupt_active",
            "interrupt_valid",
        )
        parameters = {
            "profile": "bounded_subsystem",
            "width": "4",
            "counter_width": "8",
            "irq_sources": "4",
            "max_event_cycles": "128",
            "priority": "fixed_low",
            **{name: name for name in names},
        }
        return VerificationDepthPolicy(
            "gpio_timer_interrupt",
            "gpio_timer_interrupt_qualified",
            "controller",
            tuple(sorted(parameters.items())),
        )

    @classmethod
    def _configure(cls, root: Path, mutant: int):
        rtl = root / "rtl"
        rtl.mkdir()
        shutil.copy2(FIXTURES / "gpio_timer_interrupt_qualified.sv", rtl / "gpio_timer_interrupt_qualified.sv")
        (rtl / "files.f").write_text("gpio_timer_interrupt_qualified.sv\n", encoding="utf-8")
        config = replace(
            default_config(root),
            rtl_filelists=(rtl / "files.f",),
            top_modules=("gpio_timer_interrupt_qualified",),
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
