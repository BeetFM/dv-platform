import json
from dataclasses import replace
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import unittest

from dv_platform.core.config import default_config
from dv_platform.core.models import FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.run import (
    execute_formal_run,
    execute_simulation_run,
    parse_cocotb_results,
    prepare_formal_run,
    prepare_simulation_run,
)


class SimulationRunTests(unittest.TestCase):
    def test_prepare_simulation_run_builds_paths_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", "fake-sim --flag")

            run = prepare_simulation_run(config, simulator, "fifo")

            self.assertEqual(run.command, ("fake-sim", "--flag", str(run.generated_dir)))
            self.assertEqual(run.generated_dir, repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo")
            self.assertEqual(run.run_dir, repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo")

    def test_prepare_simulation_run_uses_cocotb_runner_for_icarus(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog")

            run = prepare_simulation_run(config, simulator, "fifo")

            self.assertTrue(Path(run.command[0]).name.startswith("python"))
            self.assertEqual(run.command[1], str(run.runner_script))
            self.assertEqual(run.runner_script, repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "run_cocotb.py")

    def test_prepare_formal_run_builds_paths_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            tool = FormalToolConfig("symbiyosys", "sby -f")

            run = prepare_formal_run(config, tool, "fifo")

            self.assertEqual(run.command, ("sby", "-f", str(run.run_sby)))
            self.assertEqual(run.generated_dir, repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo")
            self.assertEqual(run.run_dir, repo / ".dv-platform" / "runs" / "formal" / "fifo")
            self.assertEqual(run.run_sby, run.run_dir / "fifo.sby")

    def test_execute_simulation_run_reports_missing_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", "fake-sim")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing_artifacts")
            self.assertTrue(run.command_path.is_file())

    def test_execute_simulation_run_captures_success_logs_and_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            simulator_script = repo / "fake_sim.py"
            simulator_script.write_text(
                "import sys\nprint('ok')\nprint(sys.argv[-1])\n",
                encoding="utf-8",
            )
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"python3 {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 0)
            self.assertIn("ok", run.stdout_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")

    def test_execute_simulation_run_captures_failure_logs_and_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            simulator_script = repo / "fake_sim.py"
            simulator_script.write_text(
                "import sys\nprint('bad', file=sys.stderr)\nraise SystemExit(5)\n",
                encoding="utf-8",
            )
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"python3 {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 5)
            self.assertIn("bad", run.stderr_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["stderr_tail"], ["bad"])

    def test_execute_simulation_run_times_out_hung_simulator(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            simulator_script = repo / "fake_hung_sim.py"
            simulator_script.write_text(
                "import time\nprint('started', flush=True)\ntime.sleep(5)\n",
                encoding="utf-8",
            )
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo", timeout_seconds=0.1)

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 124)
            self.assertIn("started", run.stdout_log.read_text(encoding="utf-8"))
            self.assertIn("timed out", run.stderr_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "timeout")
            self.assertEqual(summary["timeout_seconds"], 0.1)

    def test_execute_simulation_run_reports_malformed_cocotb_results(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator_script = repo / "fake_bad_results.py"
            results_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "results.xml"
            simulator_script.write_text(
                "from pathlib import Path\n"
                f"Path({str(results_path)!r}).write_text('<testsuites>', encoding='utf-8')\n",
                encoding="utf-8",
            )
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            prepared = prepare_simulation_run(config, simulator, "fifo")
            run = replace(prepared, runner_script=prepared.run_dir / "unused_cocotb_runner.py")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 1)
            self.assertIn("Could not parse cocotb results XML", run.stderr_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertIsNone(summary["results"])
            self.assertEqual(summary["results_parse_status"], "malformed")
            self.assertIn("Could not parse cocotb results XML", summary["results_error"])

    def test_execute_simulation_run_reports_invalid_generated_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "invalid_artifacts")
            self.assertIn("Missing generated cocotb test", summary["validation_error"])

    def test_execute_formal_run_reports_missing_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            tool = FormalToolConfig("symbiyosys", "sby")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing_artifacts")
            self.assertTrue(run.command_path.is_file())

    def test_execute_formal_run_reports_invalid_generated_artifacts(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            generated_dir.mkdir(parents=True)
            tool = FormalToolConfig("symbiyosys", "sby")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "invalid_artifacts")
            self.assertIn("Missing generated formal harness", summary["validation_error"])

    def test_execute_formal_run_invokes_tool_and_writes_summary(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            _write_valid_formal_artifacts(generated_dir, "fifo")
            _write_project_manifest(config, repo / "rtl" / "fifo.sv")
            tool_script = repo / "fake_sby.py"
            tool_script.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "sby = Path(sys.argv[-1])\n"
                "print('formal ok')\n"
                "print(sby.read_text(encoding='utf-8'))\n",
                encoding="utf-8",
            )
            tool = FormalToolConfig("symbiyosys", f"{sys.executable} {tool_script}")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 0)
            self.assertIn("formal ok", run.stdout_log.read_text(encoding="utf-8"))
            self.assertIn("read -formal -sv " + str(repo / "rtl" / "fifo.sv"), run.run_sby.read_text(encoding="utf-8"))
            self.assertIn("read -formal -sv " + str(generated_dir / "formal_fifo.sv"), run.run_sby.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["tool"], "symbiyosys")
            self.assertEqual(summary["run_sby"], str(run.run_sby))
            self.assertEqual(summary["generated_harness"], str(generated_dir / "formal_fifo.sv"))
            self.assertEqual(summary["provenance_manifest"], str(generated_dir / "provenance.json"))

    def test_execute_formal_run_reports_missing_project_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            _write_valid_formal_artifacts(generated_dir, "fifo")
            tool = FormalToolConfig("symbiyosys", "sby")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "missing_manifest")
            self.assertIn("run analyze-rtl first", summary["validation_error"])

    def test_execute_simulation_run_summarizes_cocotb_failure_details(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator_script = repo / "fake_cocotb_failure.py"
            results_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "results.xml"
            simulator_script.write_text(
                "from pathlib import Path\n"
                "print('line 1')\n"
                "print('line 2')\n"
                f"Path({str(results_path)!r}).write_text('''<testsuites><testsuite>"
                "<testcase classname=\"tb\" name=\"passes\"/>"
                "<testcase classname=\"tb\" name=\"fails\"><failure message=\"bad\"/></testcase>"
                "</testsuite></testsuites>''', encoding='utf-8')\n",
                encoding="utf-8",
            )
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            prepared = prepare_simulation_run(config, simulator, "fifo")
            run = replace(prepared, runner_script=prepared.run_dir / "unused_cocotb_runner.py")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 1)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["results_parse_status"], "parsed")
            self.assertEqual(summary["results"]["failed_testcases"], ["tb.fails"])
            self.assertEqual(summary["stdout_tail"], ["line 1", "line 2"])
            self.assertEqual(summary["generated_artifact"], str(generated_dir / "test_fifo.py"))
            self.assertEqual(summary["provenance_manifest"], str(generated_dir / "provenance.json"))

    def test_parse_cocotb_results_counts_junit_outcomes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            results_path = Path(temp_dir) / "results.xml"
            results_path.write_text(
                """<?xml version="1.0" encoding="UTF-8"?>
<testsuites>
  <testsuite name="all">
    <testcase classname="tb" name="passes"/>
    <testcase classname="tb" name="fails"><failure message="bad"/></testcase>
    <testcase classname="tb" name="errors"><error message="boom"/></testcase>
    <testcase classname="tb" name="skips"><skipped/></testcase>
  </testsuite>
</testsuites>
""",
                encoding="utf-8",
            )

            results = parse_cocotb_results(results_path)

            self.assertIsNotNone(results)
            self.assertEqual(
                results.as_dict(),
                {
                    "tests": 4,
                    "passed": 1,
                    "failures": 1,
                    "errors": 1,
                    "skipped": 1,
                    "failed_testcases": ["tb.fails", "tb.errors"],
                },
            )
            self.assertTrue(results.failed)

def _write_valid_cocotb_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / f"test_{module}.py").write_text(
        "import cocotb\n\n@cocotb.test()\nasync def test_" + module + "_smoke(dut):\n    assert dut is not None\n",
        encoding="utf-8",
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "module": module,
                "target": "cocotb",
                "artifacts": [
                    {
                        "path": f"test_{module}.py",
                        "kind": "testbench",
                        "source_plan_module": module,
                        "provenance_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
                    }
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_valid_formal_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    (generated_dir / f"formal_{module}.sv").write_text(
        "module formal_" + module + "; endmodule\n",
        encoding="utf-8",
    )
    (generated_dir / f"{module}.sby").write_text(
        "[options]\nmode prove\n",
        encoding="utf-8",
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "module": module,
                "target": "formal",
                "artifacts": [
                    {
                        "path": f"formal_{module}.sv",
                        "kind": "formal_harness",
                        "source_plan_module": module,
                        "provenance_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
                    },
                    {
                        "path": f"{module}.sby",
                        "kind": "run_script",
                        "source_plan_module": module,
                        "provenance_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_project_manifest(config, hdl_path: Path) -> None:
    hdl_path.parent.mkdir(parents=True, exist_ok=True)
    hdl_path.write_text("module fifo; endmodule\n", encoding="utf-8")
    manifest_path = config.work_dir / "project-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    manifest_path.write_text(
        json.dumps({"hdl_files": [{"path": str(hdl_path), "language": "systemverilog"}]}) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    unittest.main()
