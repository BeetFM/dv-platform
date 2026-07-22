import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import mock

import dv_platform.run as run_module
from dv_platform.core.config import default_config
from dv_platform.core.models import FormalToolConfig, SimulatorConfig, VerificationTarget
from dv_platform.run import (
    execute_formal_run,
    execute_simulation_run,
    parse_cocotb_results,
    parse_formal_results,
    parse_native_results,
    prepare_formal_run,
    prepare_simulation_run,
)


class SimulationRunTests(unittest.TestCase):
    def test_native_result_decoder_reconciles_exact_trace_identity(self) -> None:
        output = "\n".join(
            (
                "tool banner",
                'DV_PLATFORM_RESULT_V1 {"trace_id":"fifo:tb_fifo","status":"passed"}',
            )
        )

        results = parse_native_results(output, ("fifo:tb_fifo",))

        self.assertEqual(results.outcomes, (("fifo:tb_fifo", "passed"),))
        self.assertFalse(results.failed)
        ghdl_results = parse_native_results(
            'tb_fifo.vhd:20:9:@20ns:(report note): DV_PLATFORM_RESULT_V1 {"trace_id":"fifo:tb_fifo","status":"passed"}',
            ("fifo:tb_fifo",),
        )
        self.assertEqual(ghdl_results, results)
        with self.assertRaisesRegex(ValueError, "unknown or stale"):
            parse_native_results(
                'DV_PLATFORM_RESULT_V1 {"trace_id":"fifo:stale","status":"passed"}',
                ("fifo:tb_fifo",),
            )
        with self.assertRaisesRegex(ValueError, "duplicate"):
            parse_native_results(output + "\n" + output.splitlines()[-1], ("fifo:tb_fifo",))
        with self.assertRaisesRegex(ValueError, "missing generated trace IDs"):
            parse_native_results(output, ("fifo:tb_fifo", "fifo:second"))

    def test_native_simulation_requires_and_normalizes_per_trace_results(self) -> None:
        for emitted_status, expected_return_code in (("passed", 0), ("failed", 1), (None, 1)):
            with self.subTest(status=emitted_status), TemporaryDirectory() as temp_dir:
                repo = Path(temp_dir)
                generated_dir = repo / "generated" / "dv-platform" / "simulation" / "systemverilog" / "modules" / "fifo"
                _write_valid_native_artifacts(generated_dir, "fifo", "systemverilog")
                simulator_script = repo / "fake_native.py"
                marker = (
                    f'print(\'DV_PLATFORM_RESULT_V1 {{"trace_id":"fifo:tb_fifo","status":"{emitted_status}"}}\')\n'
                    if emitted_status is not None
                    else "print('native simulation completed without results')\n"
                )
                simulator_script.write_text(marker, encoding="utf-8")
                config = default_config(repo)
                simulator = SimulatorConfig(
                    VerificationTarget.SYSTEMVERILOG,
                    "fake",
                    f"{sys.executable} {simulator_script}",
                )
                run = prepare_simulation_run(config, simulator, "fifo")

                return_code = execute_simulation_run(run)

                self.assertEqual(return_code, expected_return_code)
                summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
                if emitted_status is None:
                    self.assertEqual(summary["results_parse_status"], "missing")
                    self.assertEqual(summary["validation_result"]["status"], "failed")
                    self.assertEqual(summary["verification_coverage"]["unexecuted"], 1)
                else:
                    self.assertEqual(summary["results_parse_status"], "parsed")
                    self.assertEqual(summary["native_results"]["schema_version"], 1)
                    expected = "passed" if emitted_status == "passed" else "failed"
                    self.assertEqual(summary["verification_coverage"][expected], 1)

    @unittest.skipUnless(shutil.which("iverilog") and shutil.which("vvp"), "requires Icarus Verilog")
    def test_native_iverilog_wrapper_compiles_runs_and_decodes_generated_testbench(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "systemverilog" / "modules" / "fifo"
            _write_valid_native_artifacts(generated_dir, "fifo", "systemverilog")
            simulator = SimulatorConfig(VerificationTarget.SYSTEMVERILOG, "icarus", "iverilog")
            config = replace(default_config(repo), simulators=(simulator,))
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 0)
            self.assertTrue(run.runner_script and run.runner_script.is_file())
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["validation_result"]["status"], "passed")
            self.assertEqual(summary["verification_coverage"]["passed"], 1)
            self.assertEqual(summary["tool_qualification"]["tool"], "iverilog")
            self.assertEqual(summary["tool_qualification"]["status"], "supported")

    def test_cocotb_trace_statuses_map_failed_testcase_to_generated_symbol(self) -> None:
        traces = [
            {"trace_id": "fifo:smoke", "generated_symbol": "test_fifo_smoke"},
            {"trace_id": "fifo:protocol", "generated_symbol": "test_fifo_ready_valid"},
        ]
        results = run_module.CocotbResults(
            tests=2,
            passed=1,
            failures=1,
            testcases=("tb.test_fifo_smoke", "tb.test_fifo_ready_valid"),
            failed_testcases=("tb.test_fifo_ready_valid",),
        )

        statuses = run_module._cocotb_trace_statuses(traces, results)

        self.assertEqual(statuses, {"fifo:smoke": "passed", "fifo:protocol": "failed"})

    def test_prepare_simulation_run_builds_paths_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", "fake-sim --flag")

            run = prepare_simulation_run(config, simulator, "fifo")

            self.assertEqual(run.command, ("fake-sim", "--flag", str(run.generated_dir)))
            self.assertEqual(
                run.generated_dir, repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            )
            self.assertEqual(run.run_dir, repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo")

    def test_prepare_simulation_run_uses_cocotb_runner_for_icarus(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog")

            run = prepare_simulation_run(config, simulator, "fifo")

            self.assertTrue(Path(run.command[0]).name.startswith("python"))
            self.assertEqual(run.command[1], str(run.runner_script))
            self.assertEqual(
                run.runner_script, repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "run_cocotb.py"
            )

    def test_prepare_simulation_run_rejects_empty_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "invalid", "   ")

            with self.assertRaisesRegex(ValueError, "command is empty"):
                prepare_simulation_run(config, simulator, "fifo")

    def test_prepare_formal_run_builds_paths_and_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            tool = FormalToolConfig("symbiyosys", "sby")

            run = prepare_formal_run(config, tool, "fifo")

            self.assertEqual(run.command, ("sby", "-f", "--sequential", str(run.run_sby)))
            self.assertEqual(run.generated_dir, repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo")
            self.assertEqual(run.run_dir, repo / ".dv-platform" / "runs" / "formal" / "fifo")
            self.assertEqual(run.run_sby, run.run_dir / "fifo.sby")

    def test_prepare_formal_run_rejects_empty_command(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            tool = FormalToolConfig("invalid", "   ")

            with self.assertRaisesRegex(ValueError, "command is empty"):
                prepare_formal_run(config, tool, "fifo")

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
                "from pathlib import Path\n"
                "import sys\n"
                "run_dir = Path(__file__).parent / '.dv-platform/runs/simulation/cocotb/fifo'\n"
                "run_dir.mkdir(parents=True, exist_ok=True)\n"
                "(run_dir / 'results.xml').write_text('<testsuite><testcase name=\"passes\"/></testsuite>')\n"
                "print('ok')\n"
                "print(sys.argv[-1])\n",
                encoding="utf-8",
            )
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
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
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"python3 {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 5)
            self.assertIn("bad", run.stderr_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["stderr_tail"], ["bad"])

    def test_execute_simulation_run_rejects_tampered_generated_artifact(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            (generated_dir / "test_fifo.py").write_text("# tampered\n", encoding="utf-8")
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} -c 'print(1)'")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "invalid_artifacts")
            self.assertIn("does not match provenance", summary["validation_error"])

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
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo", timeout_seconds=0.1)

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 124)
            self.assertIn("started", run.stdout_log.read_text(encoding="utf-8"))
            self.assertIn("timed out", run.stderr_log.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "timeout")
            self.assertEqual(summary["timeout_seconds"], 0.1)

    def test_execute_simulation_run_terminates_descendants_on_timeout(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            simulator_script = repo / "fake_parent_with_child.py"
            child_pid_path = repo / "child.pid"
            simulator_script.write_text(
                "import subprocess\n"
                "import sys\n"
                "import time\n"
                "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)'])\n"
                "open(sys.argv[1], 'w').write(str(child.pid))\n"
                "print('started', flush=True)\n"
                "time.sleep(30)\n",
                encoding="utf-8",
            )
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator = SimulatorConfig(
                VerificationTarget.COCOTB,
                "fake",
                f"{sys.executable} {simulator_script} {child_pid_path}",
            )
            run = prepare_simulation_run(config, simulator, "fifo", timeout_seconds=0.2)

            self.assertEqual(execute_simulation_run(run), 124)
            child_pid = int(child_pid_path.read_text(encoding="utf-8"))
            for _ in range(20):
                try:
                    os.kill(child_pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.05)
            else:
                self.fail(f"timed-out simulator child {child_pid} is still running")

    def test_bounded_process_retains_only_bounded_output(self) -> None:
        with TemporaryDirectory() as temp_dir:
            output_dir = Path(temp_dir)
            result = run_module._run_bounded_process(
                (sys.executable, "-c", "print('x' * 10000)"),
                cwd=output_dir,
                env=dict(os.environ),
                timeout_seconds=5,
                stdout_path=output_dir / "stdout.log",
                stderr_path=output_dir / "stderr.log",
                max_output_bytes=1024,
                memory_limit_mb=0,
            )

            self.assertEqual(result.returncode, 0)
            self.assertTrue(result.stdout_truncated)
            self.assertIn("output truncated", result.stdout)
            self.assertLessEqual((output_dir / "stdout.log").stat().st_size, 1100)

    def test_process_memory_limit_is_portable_and_fail_closed(self) -> None:
        with mock.patch.object(run_module.os, "name", "nt"):
            run_module._set_process_memory_limit(123, 64)
        with mock.patch("resource.prlimit", side_effect=OSError("unsupported")) as prlimit:
            run_module._set_process_memory_limit(123, 64)
        prlimit.assert_called_once()

    def test_process_group_termination_escalates_and_tolerates_missing_group(self) -> None:
        process = mock.Mock(pid=123)
        process.wait.side_effect = [subprocess.TimeoutExpired(("tool",), 0), None]
        with mock.patch.object(run_module.os, "killpg", side_effect=ProcessLookupError) as killpg:
            run_module._terminate_process_group(process, grace_seconds=0)
        self.assertEqual(killpg.call_count, 2)
        self.assertEqual(process.wait.call_count, 2)

    def test_non_posix_process_termination_uses_process_methods(self) -> None:
        process = mock.Mock()
        process.wait.side_effect = [subprocess.TimeoutExpired(("tool",), 0), None]
        with mock.patch.object(run_module.os, "name", "nt"):
            run_module._terminate_process_group(process, grace_seconds=0)
        process.terminate.assert_called_once()
        process.kill.assert_called_once()

    def test_formal_cdc_evidence_rejects_malformed_shapes_and_normalizes_outcomes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            run = prepare_formal_run(config, FormalToolConfig("symbiyosys", "sby"), "fifo")
            path = run.generated_dir / "formal_fifo_cdc.json"
            path.parent.mkdir(parents=True)
            path.write_text("{", encoding="utf-8")
            malformed = run_module._formal_cdc_verification(run, run_module.FormalResults())
            self.assertIn("Invalid CDC evidence report", malformed["error"])

            path.write_text(json.dumps({"paths": "not-a-list"}), encoding="utf-8")
            self.assertEqual(run_module._formal_cdc_verification(run, run_module.FormalResults())["paths"], [])

            path.write_text(
                json.dumps(
                    {
                        "policy": "bounded",
                        "bounded_depth": 4,
                        "paths": [
                            None,
                            {"path_id": "unsupported", "evidence_level": "unsupported"},
                            {"path_id": "failed", "evidence_level": "structural", "formal_task": "prove"},
                            {"path_id": "bounded", "evidence_level": "bounded", "formal_task": "cover"},
                            {"path_id": "unknown", "evidence_level": "structural", "formal_task": "missing"},
                            {"path_id": "passed", "evidence_level": "structural", "formal_task": "pass_task"},
                        ],
                    }
                ),
                encoding="utf-8",
            )
            evidence = run_module._formal_cdc_verification(
                run,
                run_module.FormalResults(task_status={"prove": "fail", "cover": "pass", "pass_task": "pass"}),
            )
            outcomes = {item["path_id"]: item["outcome_status"] for item in evidence["paths"]}
            self.assertEqual(
                outcomes,
                {
                    "unsupported": "unsupported",
                    "failed": "failed",
                    "bounded": "bounded_pass",
                    "unknown": "unexecuted",
                    "passed": "passed",
                },
            )
            self.assertFalse(evidence["closure_complete"])

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
                f"from pathlib import Path\nPath({str(results_path)!r}).write_text('<testsuites>', encoding='utf-8')\n",
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

    def test_execute_simulation_run_fails_when_cocotb_results_are_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            simulator_script = repo / "fake_no_results.py"
            simulator_script.write_text("print('completed without results')\n", encoding="utf-8")
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            prepared = prepare_simulation_run(config, simulator, "fifo")
            run = replace(prepared, runner_script=prepared.run_dir / "unused_cocotb_runner.py")
            run.run_dir.mkdir(parents=True)
            (run.run_dir / "results.xml").write_text(
                "<testsuites><testcase name='stale'/></testsuites>", encoding="utf-8"
            )

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 1)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["results_parse_status"], "missing")
            self.assertIn("not produced", summary["results_error"])

    def test_execute_simulation_run_fails_when_cocotb_executes_zero_tests(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            results_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "results.xml"
            simulator_script = repo / "fake_zero_tests.py"
            simulator_script.write_text(
                "from pathlib import Path\n"
                f"Path({str(results_path)!r}).write_text('<testsuites/>', encoding='utf-8')\n",
                encoding="utf-8",
            )
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            prepared = prepare_simulation_run(config, simulator, "fifo")
            run = replace(prepared, runner_script=prepared.run_dir / "unused_cocotb_runner.py")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 1)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["results"]["tests"], 0)
            self.assertIn("zero testcases", summary["results_error"])

    def test_execute_simulation_run_rejects_skipped_only_cocotb_results(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "fifo"
            _write_valid_cocotb_artifacts(generated_dir, "fifo")
            results_path = repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "fifo" / "results.xml"
            simulator_script = repo / "fake_skipped.py"
            simulator_script.write_text(
                "from pathlib import Path\n"
                f"path = Path({str(results_path)!r})\n"
                "path.parent.mkdir(parents=True, exist_ok=True)\n"
                "path.write_text('<testsuite><testcase name=\"skipped\"><skipped/></testcase></testsuite>')\n",
                encoding="utf-8",
            )
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", f"{sys.executable} {simulator_script}")
            run = prepare_simulation_run(config, simulator, "fifo")

            return_code = execute_simulation_run(run)

            self.assertEqual(return_code, 1)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertIn("no passing testcases", summary["results_error"])

    def test_prepare_run_rejects_module_path_escape(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            simulator = SimulatorConfig(VerificationTarget.COCOTB, "fake", "fake-sim")

            with self.assertRaisesRegex(ValueError, "path separators"):
                prepare_simulation_run(config, simulator, "../../outside")

            with self.assertRaisesRegex(ValueError, "control-character"):
                prepare_simulation_run(config, simulator, "fifo\nforged-output")

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
            _write_project_manifest(config, repo / "rtl" / "fifo.sv")
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
            _write_project_manifest(config, repo / "rtl" / "fifo.sv")
            _write_valid_formal_artifacts(generated_dir, "fifo")
            tool_script = repo / "fake_sby.py"
            tool_script.write_text(
                "from pathlib import Path\n"
                "import sys\n"
                "sby = Path(sys.argv[-1])\n"
                "print('formal ok')\n"
                "print('engine_0: smtbmc: Status: passed')\n"
                "print('engine_0.basecase returned pass for basecase')\n"
                "print('engine_0.induction returned pass for induction')\n"
                "print('successful proof by k-induction')\n"
                "print('DONE (PASS, rc=0)')\n"
                "print(sby.read_text(encoding='utf-8'))\n",
                encoding="utf-8",
            )
            tool = FormalToolConfig("symbiyosys", f"{sys.executable} {tool_script}")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 0)
            self.assertIn("formal ok", run.stdout_log.read_text(encoding="utf-8"))
            self.assertIn(
                'read -formal -sv "' + str(repo / "rtl" / "fifo.sv") + '"',
                run.run_sby.read_text(encoding="utf-8"),
            )
            self.assertIn(
                'read -formal -sv "' + str(generated_dir / "formal_fifo.sv") + '"',
                run.run_sby.read_text(encoding="utf-8"),
            )
            self.assertIn("smtbmc z3", run.run_sby.read_text(encoding="utf-8"))
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["tool"], "symbiyosys")
            self.assertEqual(summary["run_sby"], str(run.run_sby))
            self.assertEqual(summary["generated_harness"], str(generated_dir / "formal_fifo.sv"))
            self.assertEqual(summary["provenance_manifest"], str(generated_dir / "provenance.json"))
            self.assertEqual(summary["formal_status"], "pass")
            self.assertEqual(summary["engine_status"], {"basecase": "pass", "induction": "pass"})
            self.assertEqual(summary["proof_method"], "k-induction")
            self.assertIsNone(summary["formal_error"])
            self.assertEqual(summary["trace_paths"], [])

    def test_execute_formal_run_summarizes_trace_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            _write_project_manifest(config, repo / "rtl" / "fifo.sv")
            _write_valid_formal_artifacts(generated_dir, "fifo")
            tool_script = repo / "fake_sby_fail.py"
            tool_script.write_text(
                "print('summary: counterexample trace [basecase]: engine_0/trace.vcd')\n"
                "print('Writing trace to Yosys witness file: engine_0/trace.yw')\n"
                "print('DONE (FAIL, rc=2)')\n"
                "raise SystemExit(2)\n",
                encoding="utf-8",
            )
            tool = FormalToolConfig("symbiyosys", f"{sys.executable} {tool_script}")
            run = prepare_formal_run(config, tool, "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 2)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["status"], "failed")
            self.assertEqual(summary["formal_status"], "fail")
            self.assertEqual(
                summary["trace_paths"],
                [
                    str(run.run_dir / "fifo" / "engine_0" / "trace.vcd"),
                    str(run.run_dir / "fifo" / "engine_0" / "trace.yw"),
                ],
            )

    def test_execute_formal_run_rejects_unknown_result_even_with_zero_exit(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "fifo"
            _write_project_manifest(config, repo / "rtl" / "fifo.sv")
            _write_valid_formal_artifacts(generated_dir, "fifo")
            tool_script = repo / "fake_sby_unknown.py"
            tool_script.write_text("print('tool exited without a proof result')\n", encoding="utf-8")
            run = prepare_formal_run(config, FormalToolConfig("symbiyosys", f"{sys.executable} {tool_script}"), "fifo")

            return_code = execute_formal_run(config, run)

            self.assertEqual(return_code, 1)
            summary = json.loads(run.summary_path.read_text(encoding="utf-8"))
            self.assertEqual(summary["formal_status"], "unknown")
            self.assertEqual(summary["status"], "failed")

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
                '<testcase classname="tb" name="passes"/>'
                '<testcase classname="tb" name="fails"><failure message="bad"/></testcase>'
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
            self.assertEqual(summary["verification_coverage"]["failed"], 0)
            self.assertEqual(summary["verification_coverage"]["unexecuted"], 1)
            self.assertFalse(summary["verification_coverage"]["complete"])
            self.assertEqual(summary["failure_traceability"], [])
            self.assertEqual(summary["triage"]["category"], "rtl_or_requirement_mismatch")

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
                    "testcases": ["tb.passes", "tb.fails", "tb.errors", "tb.skips"],
                    "failed_testcases": ["tb.fails", "tb.errors"],
                },
            )
            self.assertTrue(results.failed)

    def test_parse_cocotb_results_rejects_entities_and_symlinks(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            results_path = root / "results.xml"
            results_path.write_text('<!DOCTYPE x [<!ENTITY e "bad">]><testsuites>&e;</testsuites>', encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "DTD or entity"):
                parse_cocotb_results(results_path)

            target = root / "target.xml"
            target.write_text("<testsuites/>", encoding="utf-8")
            results_path.unlink()
            results_path.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                parse_cocotb_results(results_path)

    def test_parse_formal_results_extracts_symbiyosys_status(self) -> None:
        results = parse_formal_results(
            "\n".join(
                [
                    "engine_0.basecase returned pass for basecase",
                    "engine_0.induction returned pass for induction",
                    "successful proof by k-induction",
                    "DONE (PASS, rc=0)",
                ]
            )
        )

        self.assertEqual(
            results.as_dict(),
            {
                "formal_status": "pass",
                "engine_status": {"basecase": "pass", "induction": "pass"},
                "task_status": {},
                "proof_method": "k-induction",
                "formal_error": None,
                "trace_paths": [],
            },
        )

    def test_parse_formal_results_extracts_errors(self) -> None:
        results = parse_formal_results(
            "\n".join(
                [
                    "engine_0.basecase returned fail for basecase",
                    "ERROR: failed to parse design",
                    "summary: counterexample trace [basecase]: /tmp/run/engine_0/trace.vcd",
                    "Writing trace to Yosys witness file: engine_0/trace.yw",
                    "DONE (ERROR, rc=16)",
                ]
            )
        )

        self.assertEqual(results.formal_status, "error")
        self.assertEqual(results.engine_status, {"basecase": "fail"})
        self.assertEqual(results.formal_error, "ERROR: failed to parse design")
        self.assertEqual(results.trace_paths, ("/tmp/run/engine_0/trace.vcd", "engine_0/trace.yw"))

    def test_parse_formal_results_tracks_prove_and_cover_tasks(self) -> None:
        results = parse_formal_results(
            "\n".join(("SBY [design_prove] prove DONE (PASS, rc=0)", "SBY [design_cover] cover DONE (FAIL, rc=1)"))
        )

        self.assertEqual(results.task_status, {"prove": "pass", "cover": "fail"})

    def test_parse_formal_results_tracks_bounded_cdc_task(self) -> None:
        results = parse_formal_results("SBY [design_cdc_bmc] cdc_bmc DONE (PASS, rc=0)")

        self.assertEqual(results.task_status, {"cdc_bmc": "pass"})

    def test_parse_formal_results_does_not_mask_unknown_induction_with_subtask_pass(self) -> None:
        results = parse_formal_results(
            "\n".join(
                [
                    "engine_0.basecase returned pass for basecase",
                    "prove.basecase: DONE (PASS, rc=0)",
                    "engine_0.induction returned fail for induction",
                    "prove: DONE (UNKNOWN, rc=4)",
                ]
            )
        )

        self.assertEqual(results.formal_status, "unknown")
        self.assertEqual(results.engine_status, {"basecase": "pass", "induction": "fail"})

    def test_parse_formal_results_handles_uppercase_symbiyosys_summary(self) -> None:
        results = parse_formal_results(
            "\n".join(
                [
                    "Status returned by engine for basecase: PASS",
                    "summary: engine_0 (smtbmc) returned PASS for induction",
                    "DONE (PASS, rc=0)",
                ]
            )
        )

        self.assertEqual(results.formal_status, "pass")
        self.assertEqual(results.engine_status, {"basecase": "pass", "induction": "pass"})


def _write_valid_cocotb_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    repo = generated_dir.parents[5]
    _write_project_manifest(default_config(repo), repo / "rtl" / f"{module}.sv")
    test_path = generated_dir / f"test_{module}.py"
    test_path.write_text(
        "import cocotb\n\n@cocotb.test()\nasync def test_" + module + "_smoke(dut):\n    assert dut is not None\n",
        encoding="utf-8",
    )
    traceability = _traceability(module, f"test_{module}_smoke")
    execution_path = _write_execution_manifest(
        generated_dir,
        module,
        "cocotb",
        ((test_path.name, "testbench", traceability[0]["trace_id"]),),
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": "cocotb",
                "artifacts": [
                    {
                        "path": f"test_{module}.py",
                        "kind": "testbench",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
                        "size_bytes": test_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": traceability,
                    },
                    {
                        "path": execution_path.name,
                        "kind": "report",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(execution_path.read_bytes()).hexdigest(),
                        "size_bytes": execution_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_valid_native_artifacts(generated_dir: Path, module: str, target: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    repo = generated_dir.parents[5]
    config = default_config(repo)
    _write_project_manifest(config, repo / "rtl" / f"{module}.sv")
    extension = "sv" if target == "systemverilog" else "v"
    test_path = generated_dir / f"tb_{module}.{extension}"
    test_path.write_text(
        "module tb_"
        + module
        + ";\n    "
        + module
        + " dut();\n    initial begin\n"
        + f'        $display("DV_PLATFORM_RESULT_V1 {{\\"trace_id\\":\\"{module}:tb_{module}\\",'
        + '\\"status\\":\\"passed\\"}");\n'
        + "        $finish;\n    end\nendmodule\n",
        encoding="utf-8",
    )
    traceability = _traceability(module, f"tb_{module}")
    execution_path = _write_execution_manifest(
        generated_dir,
        module,
        target,
        ((test_path.name, "testbench", traceability[0]["trace_id"]),),
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": target,
                "artifacts": [
                    {
                        "path": test_path.name,
                        "kind": "testbench",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(test_path.read_bytes()).hexdigest(),
                        "size_bytes": test_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": traceability,
                    },
                    {
                        "path": execution_path.name,
                        "kind": "report",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(execution_path.read_bytes()).hexdigest(),
                        "size_bytes": execution_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                    },
                ],
            }
        )
        + "\n",
        encoding="utf-8",
    )


def _write_valid_formal_artifacts(generated_dir: Path, module: str) -> None:
    generated_dir.mkdir(parents=True, exist_ok=True)
    harness_path = generated_dir / f"formal_{module}.sv"
    harness_path.write_text(
        "module formal_" + module + "; endmodule\n",
        encoding="utf-8",
    )
    sby_path = generated_dir / f"{module}.sby"
    sby_path.write_text(
        "[options]\nmode prove\n",
        encoding="utf-8",
    )
    harness_trace = _traceability(module, f"formal_{module}_properties")
    sby_trace = _traceability(module, f"formal_{module}_run")
    execution_path = _write_execution_manifest(
        generated_dir,
        module,
        "formal",
        (
            (harness_path.name, "formal_harness", harness_trace[0]["trace_id"]),
            (sby_path.name, "run_script", sby_trace[0]["trace_id"]),
        ),
    )
    (generated_dir / "provenance.json").write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": "formal",
                "artifacts": [
                    {
                        "path": f"formal_{module}.sv",
                        "kind": "formal_harness",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(harness_path.read_bytes()).hexdigest(),
                        "size_bytes": harness_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": harness_trace,
                    },
                    {
                        "path": f"{module}.sby",
                        "kind": "run_script",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(sby_path.read_bytes()).hexdigest(),
                        "size_bytes": sby_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
                        "traceability": sby_trace,
                    },
                    {
                        "path": execution_path.name,
                        "kind": "report",
                        "source_plan_module": module,
                        "content_sha256": hashlib.sha256(execution_path.read_bytes()).hexdigest(),
                        "size_bytes": execution_path.stat().st_size,
                        "provenance_refs": [
                            {"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}
                        ],
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


def _traceability(module: str, symbol: str) -> list[dict[str, object]]:
    return [
        {
            "trace_id": f"{module}:{symbol}",
            "generated_symbol": symbol,
            "check_indexes": [1],
            "requirement_ids": [f"{module}:requirement"],
            "behavior_ids": [f"{module}:behavior"],
            "claim_ids": [f"{module}:claim"],
            "evidence_refs": [{"kind": "verilator_ast", "source_id": "Vfifo.xml", "locator": f"module:{module}"}],
        }
    ]


def _write_execution_manifest(
    generated_dir: Path,
    module: str,
    target: str,
    files: tuple[tuple[str, str, str], ...],
) -> Path:
    path = generated_dir / "execution-manifest.json"
    repo = generated_dir.parents[4] if target == "formal" else generated_dir.parents[5]
    project_manifest_path = repo / ".dv-platform" / "project-manifest.json"
    project_payload = (
        json.loads(project_manifest_path.read_text(encoding="utf-8")) if project_manifest_path.is_file() else {}
    )
    hdl_files = []
    for item in project_payload.get("hdl_files", []):
        source = Path(item["path"])
        hdl_files.append(
            {
                **item,
                "size_bytes": source.stat().st_size,
                "content_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
            }
        )
    path.write_text(
        json.dumps(
            {
                "schema_version": 2,
                "module": module,
                "target": target,
                "adapter": {"kind": "formal" if target == "formal" else "simulation"},
                "generated_files": [
                    {"path": file_path, "kind": kind, "trace_ids": [trace_id]} for file_path, kind, trace_id in files
                ],
                "project": {
                    "manifest_path": str(project_manifest_path) if project_manifest_path.is_file() else None,
                    "manifest_sha256": (
                        hashlib.sha256(project_manifest_path.read_bytes()).hexdigest()
                        if project_manifest_path.is_file()
                        else None
                    ),
                    "hdl_files": hdl_files,
                    "include_paths": project_payload.get("include_paths", []),
                    "defines": project_payload.get("defines", []),
                    "top_modules": project_payload.get("top_modules", []),
                },
            },
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return path


if __name__ == "__main__":
    unittest.main()
