import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.core.config import default_config
from dv_platform.core.models import SimulatorConfig, VerificationTarget
from dv_platform.run import execute_simulation_run, prepare_simulation_run


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


if __name__ == "__main__":
    unittest.main()
