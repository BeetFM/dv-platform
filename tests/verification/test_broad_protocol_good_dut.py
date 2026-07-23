import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.protocols import protocol_profile
from dv_platform.analysis.plan_store import read_stored_plans
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import FormalToolConfig, ProductionProtocolBinding, SimulatorConfig, VerificationTarget
from tests.support.paths import FIXTURES_ROOT

FIXTURE = FIXTURES_ROOT / "mutations" / "protocol" / "broad_protocol_endpoints.sv"
PROFILE_PREFIX_ROLE = (
    ("axi4-1.0", "x_", "subordinate"),
    ("wishbone-b4-1.0", "wb_", "device"),
    ("avalon-mm-1.0", "mm_", "agent"),
    ("avalon-st-1.0", "ast_", "sink"),
    ("ahb-1.0", "h_", "subordinate"),
    ("tilelink-ul-uh-1.0", "tl_", "subordinate"),
)


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class BroadProtocolGoodDutTests(unittest.TestCase):
    MUTANTS = {
        1: "AXI request acceptance removed",
        2: "AXI write response dropped",
        3: "Wishbone acknowledgement dropped",
        4: "Avalon-MM read response dropped",
        5: "Avalon-ST readiness removed",
        6: "AHB readiness removed",
        7: "TileLink response dropped",
    }

    def test_all_nonstream_profiles_complete_one_full_cli_run(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "rtl"
            rtl.mkdir()
            shutil.copy2(FIXTURE, rtl / FIXTURE.name)
            (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
            bindings = self._bindings()
            config = replace(
                default_config(root),
                rtl_filelists=(rtl / "files.f",),
                top_modules=("broad_protocol_endpoints",),
                production_protocol_bindings=bindings,
                simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            )
            write_config(config, root / "dv-platform.toml")
            for command in (
                ("analyze-rtl",),
                ("plan", "--target", "cocotb"),
                ("generate", "--target", "cocotb"),
            ):
                self.assertEqual(self._cli(root, *command), 0)
            generated = config.output_dir / "simulation" / "cocotb" / "modules" / "broad_protocol_endpoints"
            first = {path.name: path.read_bytes() for path in generated.iterdir() if path.is_file()}
            self.assertEqual(self._cli(root, "generate", "--target", "cocotb"), 0)
            self.assertEqual(first, {path.name: path.read_bytes() for path in generated.iterdir() if path.is_file()})
            plan = read_stored_plans(config.work_dir / "plans" / "plans.sqlite")[0]
            self.assertEqual(
                {
                    model.profile_id
                    for model in plan.protocol_models
                    if model.profile_id in {item[0] for item in PROFILE_PREFIX_ROLE}
                },
                {item[0] for item in PROFILE_PREFIX_ROLE},
            )
            result = self._cli(root, "run", "--target", "cocotb", "--module", "broad_protocol_endpoints")
            run_dir = config.work_dir / "runs" / "simulation" / "cocotb" / "broad_protocol_endpoints"
            diagnostics = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                if path.is_file()
            )
            self.assertEqual(result, 0, diagnostics)
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["validation_result"]["status"], "passed")
            self.assertTrue(summary["verification_coverage"]["closure_complete"])
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            self.assertEqual(self._cli(root, "status", "--policy", "ci", "--no-require-tools"), 0)

    def test_each_broad_protocol_kills_a_hardware_completion_mutant(self) -> None:
        for mutant, label in self.MUTANTS.items():
            with self.subTest(mutant=label), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("broad_protocol_endpoints",),
                    parameter_overrides=(f"MUTANT={mutant}",),
                    production_protocol_bindings=self._bindings(),
                    simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "cocotb"),
                    ("generate", "--target", "cocotb"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(root, "run", "--target", "cocotb", "--module", "broad_protocol_endpoints")
                self.assertNotEqual(result, 0, f"generated broad-protocol collateral did not kill {label}")
                summary = json.loads(
                    (
                        config.work_dir / "runs" / "simulation" / "cocotb" / "broad_protocol_endpoints" / "summary.json"
                    ).read_text(encoding="utf-8")
                )
                self.assertEqual(summary["validation_result"]["status"], "failed")

    def test_native_systemverilog_and_verilog_profiles_execute(self) -> None:
        for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
            with self.subTest(target=target), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("broad_protocol_endpoints",),
                    production_protocol_bindings=self._bindings(),
                    simulators=(SimulatorConfig(target, "icarus", "iverilog"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", target.value),
                    ("generate", "--target", target.value),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(
                    root,
                    "run",
                    "--target",
                    target.value,
                    "--module",
                    "broad_protocol_endpoints",
                )
                run_dir = config.work_dir / "runs" / "simulation" / target.value / "broad_protocol_endpoints"
                diagnostics = "\n".join(
                    path.read_text(encoding="utf-8", errors="replace")
                    for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                    if path.is_file()
                )
                generated = (
                    config.output_dir
                    / "simulation"
                    / target.value
                    / "modules"
                    / "broad_protocol_endpoints"
                    / (
                        "tb_broad_protocol_endpoints.sv"
                        if target == VerificationTarget.SYSTEMVERILOG
                        else "tb_broad_protocol_endpoints.v"
                    )
                )
                if generated.is_file():
                    source_lines = generated.read_text(encoding="utf-8").splitlines()
                    diagnostics += "\n" + "\n".join(
                        f"{index + 1}: {line}" for index, line in enumerate(source_lines) if 365 <= index + 1 <= 390
                    )
                self.assertEqual(result, 0, diagnostics)
                summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                self.assertEqual(summary["validation_result"]["status"], "passed")

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_all_nonstream_profiles_complete_bounded_formal_run(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "rtl"
            rtl.mkdir()
            shutil.copy2(FIXTURE, rtl / FIXTURE.name)
            (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
            config = replace(
                default_config(root),
                rtl_filelists=(rtl / "files.f",),
                top_modules=("broad_protocol_endpoints",),
                production_protocol_bindings=self._bindings(),
                formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
            )
            write_config(config, root / "dv-platform.toml")
            for command in (
                ("analyze-rtl",),
                ("plan", "--target", "formal"),
                ("generate", "--target", "formal"),
            ):
                self.assertEqual(self._cli(root, *command), 0)
            result = self._cli(root, "run", "--target", "formal", "--module", "broad_protocol_endpoints")
            run_dir = config.work_dir / "runs" / "formal" / "broad_protocol_endpoints"
            diagnostics = "\n".join(
                path.read_text(encoding="utf-8", errors="replace")
                for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                if path.is_file()
            )
            generated = (
                config.output_dir
                / "formal"
                / "modules"
                / "broad_protocol_endpoints"
                / "formal_broad_protocol_endpoints.sv"
            )
            source_lines = generated.read_text(encoding="utf-8").splitlines()
            diagnostics += "\n" + "\n".join(
                f"{index + 1}: {line}" for index, line in enumerate(source_lines) if 368 <= index + 1 <= 382
            )
            self.assertEqual(result, 0, "\n".join(diagnostics.splitlines()[-160:]))
            summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
            self.assertEqual(summary["validation_result"]["status"], "passed")

    @staticmethod
    def _bindings() -> tuple[ProductionProtocolBinding, ...]:
        source = FIXTURE.read_text(encoding="utf-8")
        return tuple(
            ProductionProtocolBinding(
                profile_id,
                "broad_protocol_endpoints",
                prefix.rstrip("_"),
                role,
                tuple(
                    (signal.name, prefix + signal.name)
                    for signal in protocol_profile(profile_id).signals
                    if (prefix + signal.name) in source
                ),
            )
            for profile_id, prefix, role in PROFILE_PREFIX_ROLE
        )

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
