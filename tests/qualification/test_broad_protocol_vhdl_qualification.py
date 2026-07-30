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
from tests.support.paths import FIXTURES_ROOT

FIXTURE = FIXTURES_ROOT / "mutations" / "protocol" / "broad_protocol_endpoints.vhd"
PROFILE_PREFIX_ROLE = (
    ("axi4-1.0", "x_", "subordinate"),
    ("wishbone-b4-1.0", "wb_", "device"),
    ("avalon-mm-1.0", "mm_", "agent"),
    ("avalon-st-1.0", "ast_", "sink"),
    ("ahb-1.0", "h_", "subordinate"),
    ("tilelink-ul-uh-1.0", "tl_", "subordinate"),
)


@unittest.skipUnless(shutil.which("ghdl"), "requires GHDL")
class BroadProtocolVhdlQualificationTests(unittest.TestCase):
    def test_all_broad_vhdl_profiles_close_and_kill_completion_mutants(self) -> None:
        for mutant in range(8):
            with self.subTest(mutant=mutant), TemporaryDirectory() as directory:
                root = Path(directory)
                rtl = root / "rtl"
                rtl.mkdir()
                shutil.copy2(FIXTURE, rtl / FIXTURE.name)
                (rtl / "files.f").write_text(FIXTURE.name + "\n", encoding="utf-8")
                config = replace(
                    default_config(root),
                    rtl_filelists=(rtl / "files.f",),
                    top_modules=("broad_protocol_endpoints_vhdl",),
                    parameter_overrides=(f"MUTANT={mutant}",),
                    production_protocol_bindings=self._bindings(),
                    simulators=(SimulatorConfig(VerificationTarget.VHDL, "ghdl", "ghdl"),),
                )
                write_config(config, root / "dv-platform.toml")
                for command in (
                    ("analyze-rtl",),
                    ("plan", "--target", "vhdl"),
                    ("generate", "--target", "vhdl"),
                ):
                    self.assertEqual(self._cli(root, *command), 0)
                result = self._cli(root, "run", "--target", "vhdl", "--module", "broad_protocol_endpoints_vhdl")
                run_dir = config.work_dir / "runs" / "simulation" / "vhdl" / "broad_protocol_endpoints_vhdl"
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
                    self.assertNotEqual(result, 0, diagnostics)

    @staticmethod
    def _bindings() -> tuple[ProductionProtocolBinding, ...]:
        source = FIXTURE.read_text(encoding="utf-8")
        return tuple(
            ProductionProtocolBinding(
                profile_id,
                "broad_protocol_endpoints_vhdl",
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
        with redirect_stdout(StringIO()):
            return main(["--repo-root", str(root), *arguments])


if __name__ == "__main__":
    unittest.main()
