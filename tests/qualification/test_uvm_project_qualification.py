import json
import shutil
import sys
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import SimulatorConfig, VerificationTarget
from dv_platform.qualification_assets import vivado_xsim_project_runner
from dv_platform.qualification_assets.vivado_xsim_runner import CommandResult

FIXTURE = Path(__file__).parent / "fixtures" / "mutations" / "ready_valid_qualified.sv"


class UVMProjectQualificationTests(unittest.TestCase):
    def test_vivado_project_runner_requires_non_vacuous_summary_and_emits_exact_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            generated = root / "generated"
            generated.mkdir()
            rtl = root / "stream.sv"
            rtl.write_text("module stream; endmodule\n", encoding="utf-8")
            for name in ("stream_if.sv", "stream_pkg.sv", "tb_stream_uvm.sv"):
                (generated / name).write_text("// generated\n", encoding="utf-8")
            manifest = {
                "target": "uvm",
                "module": "stream",
                "generated_files": [
                    {"path": "stream_if.sv", "trace_ids": ["stream:stream_if"]},
                    {"path": "stream_pkg.sv", "trace_ids": ["stream:stream_test"]},
                    {"path": "tb_stream_uvm.sv", "trace_ids": ["stream:tb_stream_uvm"]},
                ],
                "project": {"hdl_files": [{"path": str(rtl), "language": "systemverilog"}]},
            }
            (generated / "execution-manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
            output = "Running test stream_test...\nUVM_ERROR : 0\nUVM_FATAL : 0"
            with (
                patch.object(vivado_xsim_project_runner, "_resolve_tools", return_value={}),
                patch.object(vivado_xsim_project_runner, "_run_pipeline", return_value=CommandResult(0, output)),
                redirect_stdout(captured := StringIO()),
            ):
                self.assertEqual(vivado_xsim_project_runner.main(["--vivado-bin", str(root), str(generated)]), 0)
            self.assertEqual(captured.getvalue().count('"status":"passed"'), 3)
            self.assertFalse(
                vivado_xsim_project_runner._project_passed(output + "\nno transactions were compared", "stream")
            )

    @unittest.skipUnless(
        shutil.which("verilator"),
        "requires Verilator for RTL analysis",
    )
    def test_generated_uvm_project_closes_normalized_cli_coverage(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "rtl"
            rtl.mkdir()
            shutil.copy2(FIXTURE, rtl / "ready_valid_qualified.sv")
            (rtl / "files.f").write_text("ready_valid_qualified.sv\n", encoding="utf-8")
            runner = root / "qualified_uvm_runner.py"
            runner.write_text(
                "import json,sys\n"
                "from pathlib import Path\n"
                "m=json.loads((Path(sys.argv[1])/'execution-manifest.json').read_text())\n"
                "print('Running test ready_valid_qualified_test...')\n"
                "print('UVM_ERROR : 0\\nUVM_FATAL : 0')\n"
                "for f in m['generated_files']:\n"
                " for t in f.get('trace_ids',[]): print('DV_PLATFORM_RESULT_V1 '+json.dumps({'trace_id':t,'status':'passed'},separators=(',',':')))\n",
                encoding="utf-8",
            )
            config = replace(
                default_config(root),
                rtl_filelists=(rtl / "files.f",),
                top_modules=("ready_valid_qualified",),
                simulators=(SimulatorConfig(VerificationTarget.UVM, "vivado_xsim", f"{sys.executable} {runner}"),),
            )
            write_config(config, root / "dv-platform.toml")
            for command in ("analyze-rtl", "plan", "generate"):
                args = (command, "--target", "uvm") if command != "analyze-rtl" else (command,)
                self.assertEqual(self._cli(root, *args), 0)
            package = (
                config.output_dir
                / "simulation"
                / "uvm"
                / "modules"
                / "ready_valid_qualified"
                / "ready_valid_qualified_pkg.sv"
            ).read_text(encoding="utf-8")
            self.assertIn("vif.rst <= 1'b1;", package)
            self.assertIn("repeat (3) @(posedge vif.clk);", package)
            self.assertIn("vif.rst <= 1'b0;", package)
            self.assertEqual(self._cli(root, "run", "--target", "uvm", "--module", "ready_valid_qualified"), 0)
            summary = json.loads(
                (config.work_dir / "runs" / "simulation" / "uvm" / "ready_valid_qualified" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(summary["validation_result"]["status"], "passed")
            self.assertTrue(summary["verification_coverage"]["complete"])
            self.assertGreater(summary["verification_coverage"]["passed"], 0)
            self.assertEqual(self._cli(root, "coverage", "--from-runs"), 0)
            status_output = StringIO()
            with redirect_stdout(status_output):
                status_result = main(["--repo-root", str(root), "status", "--policy", "ci", "--no-require-tools"])
            self.assertEqual(status_result, 0, status_output.getvalue())

    @staticmethod
    def _cli(root: Path, *arguments: str) -> int:
        with redirect_stdout(StringIO()):
            return main(["--repo-root", str(root), *arguments])


if __name__ == "__main__":
    unittest.main()
