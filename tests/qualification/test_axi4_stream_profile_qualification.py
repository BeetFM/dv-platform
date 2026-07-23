import json
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.protocols import protocol_profile
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import (
    FormalToolConfig,
    ProductionProtocolBinding,
    SimulatorConfig,
    VerificationTarget,
)

FIXTURE = Path(__file__).parent / "fixtures" / "mutations" / "axi4_stream_profile_source.sv"


@unittest.skipUnless(
    shutil.which("verilator") and shutil.which("iverilog") and shutil.which("cocotb-config"),
    "requires Verilator, Icarus, and cocotb",
)
class Axi4StreamProfileQualificationTests(unittest.TestCase):
    def test_generated_profile_trace_closes_good_source_and_kills_packet_mutants(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        aliases = tuple((signal.name, signal.name) for signal in profile.signals)
        for mutant in range(5):
            with self.subTest(mutant=mutant), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("axi4_stream_profile_source",),
                    parameter_overrides=(f"MUTANT={mutant}",),
                    production_protocol_bindings=(
                        ProductionProtocolBinding(
                            profile.profile_id,
                            "axi4_stream_profile_source",
                            "axis",
                            "source",
                            aliases,
                        ),
                    ),
                    simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "cocotb"),
                    ("generate", "--target", "cocotb"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(
                    root,
                    "run",
                    "--target",
                    "cocotb",
                    "--module",
                    "axi4_stream_profile_source",
                )
                summary_path = (
                    config.work_dir / "runs" / "simulation" / "cocotb" / "axi4_stream_profile_source" / "summary.json"
                )
                summary = json.loads(summary_path.read_text(encoding="utf-8"))
                if mutant == 0:
                    run_dir = summary_path.parent
                    diagnostics = "\n".join(
                        path.read_text(encoding="utf-8", errors="replace")
                        for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                        if path.is_file()
                    )
                    diagnostics = "\n".join(diagnostics.splitlines()[-120:])
                    self.assertEqual(result, 0, diagnostics)
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                    self.assertTrue(summary["verification_coverage"]["closure_complete"])
                else:
                    self.assertNotEqual(result, 0, f"AXI4-Stream profile mutant {mutant} survived")
                    self.assertEqual(summary["validation_result"]["status"], "failed")

    def test_native_profile_tasks_kill_the_same_packet_mutants(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        aliases = tuple((signal.name, signal.name) for signal in profile.signals)
        for target in (VerificationTarget.SYSTEMVERILOG, VerificationTarget.VERILOG):
            for mutant in range(5):
                with self.subTest(target=target, mutant=mutant), TemporaryDirectory() as directory:
                    root = Path(directory)
                    rtl = root / "rtl"
                    rtl.mkdir()
                    shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                    (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                    config = replace(
                        default_config(root),
                        rtl_filelists=(rtl / "files.f",),
                        top_modules=("axi4_stream_profile_source",),
                        parameter_overrides=(f"MUTANT={mutant}",),
                        production_protocol_bindings=(
                            ProductionProtocolBinding(
                                profile.profile_id,
                                "axi4_stream_profile_source",
                                "axis",
                                "source",
                                aliases,
                            ),
                        ),
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
                        "axi4_stream_profile_source",
                    )
                    if mutant == 0:
                        self.assertEqual(result, 0)
                    else:
                        self.assertNotEqual(
                            result,
                            0,
                            f"native {target.value} AXI4-Stream mutant {mutant} survived",
                        )

    @unittest.skipUnless(
        shutil.which("sby") and shutil.which("yosys") and shutil.which("z3"),
        "requires SymbiYosys, Yosys, and Z3",
    )
    def test_formal_profile_properties_kill_packet_and_stability_mutants(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        aliases = tuple((signal.name, signal.name) for signal in profile.signals)
        for mutant in range(5):
            with self.subTest(mutant=mutant), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("axi4_stream_profile_source",),
                    parameter_overrides=(f"MUTANT={mutant}",),
                    production_protocol_bindings=(
                        ProductionProtocolBinding(
                            profile.profile_id,
                            "axi4_stream_profile_source",
                            "axis",
                            "source",
                            aliases,
                        ),
                    ),
                    formal_tools=(FormalToolConfig("symbiyosys", "sby"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "formal"),
                    ("generate", "--target", "formal"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(
                    root,
                    "run",
                    "--target",
                    "formal",
                    "--module",
                    "axi4_stream_profile_source",
                )
                if mutant == 0:
                    run_dir = config.work_dir / "runs" / "formal" / "axi4_stream_profile_source"
                    diagnostics = "\n".join(
                        path.read_text(encoding="utf-8", errors="replace")
                        for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                        if path.is_file()
                    )
                    diagnostics = "\n".join(diagnostics.splitlines()[-120:])
                    self.assertEqual(result, 0, diagnostics)
                else:
                    self.assertNotEqual(result, 0, f"formal AXI4-Stream mutant {mutant} survived")

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
