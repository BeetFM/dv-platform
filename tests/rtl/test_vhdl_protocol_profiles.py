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
from dv_platform.core.models import ProductionProtocolBinding, SimulatorConfig, VerificationTarget

FIXTURE = Path(__file__).parent / "fixtures" / "mutations" / "axi4_stream_profile_source.vhd"


@unittest.skipUnless(shutil.which("ghdl"), "requires GHDL")
class VhdlProtocolProfileQualificationTests(unittest.TestCase):
    def test_axi4_stream_profile_closes_good_dut_and_kills_packet_mutants(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        source = FIXTURE.read_text(encoding="utf-8")
        aliases = tuple((signal.name, signal.name) for signal in profile.signals if signal.name in source)
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
                    top_modules=("axi4_stream_profile_source_vhdl",),
                    parameter_overrides=(f"MUTANT={mutant}",),
                    production_protocol_bindings=(
                        ProductionProtocolBinding(
                            profile.profile_id,
                            "axi4_stream_profile_source_vhdl",
                            "axis",
                            "source",
                            aliases,
                        ),
                    ),
                    simulators=(SimulatorConfig(VerificationTarget.VHDL, "ghdl", "ghdl"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "vhdl"),
                    ("generate", "--target", "vhdl"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(
                    root,
                    "run",
                    "--target",
                    "vhdl",
                    "--module",
                    "axi4_stream_profile_source_vhdl",
                )
                run_dir = config.work_dir / "runs" / "simulation" / "vhdl" / "axi4_stream_profile_source_vhdl"
                diagnostics = "\n".join(
                    path.read_text(encoding="utf-8", errors="replace")
                    for path in (run_dir / "stdout.log", run_dir / "stderr.log")
                    if path.is_file()
                )
                if mutant == 0:
                    self.assertEqual(result, 0, diagnostics)
                    summary = json.loads((run_dir / "summary.json").read_text(encoding="utf-8"))
                    self.assertEqual(summary["validation_result"]["status"], "passed")
                else:
                    self.assertNotEqual(result, 0, f"VHDL AXI4-Stream mutant {mutant} survived")

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
