import hashlib
import io
import json
import os
import shutil
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.analysis.discovery import discover_project
from dv_platform.analysis.rtl import normalize_verilator_xml, run_verilator_xml, write_normalized_rtl_facts
from dv_platform.cli import main
from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, load_config, normalize_config, write_config
from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget

FIXTURES = Path(__file__).parent / "fixtures"


def _tool_path(name: str) -> Path | None:
    found = shutil.which(name)
    if found:
        return Path(found)
    for bin_dir in _candidate_oss_cad_bins():
        candidate = bin_dir / name
        if candidate.is_file():
            return candidate
    return None


def _candidate_oss_cad_bins() -> tuple[Path, ...]:
    opt_dir = Path.home() / ".local" / "opt"
    fixed = opt_dir / "oss-cad-suite-20260625" / "oss-cad-suite" / "bin"
    candidates = [fixed]
    if opt_dir.is_dir():
        candidates.extend(sorted(opt_dir.glob("oss-cad-suite-*/oss-cad-suite/bin"), reverse=True))
    return tuple(dict.fromkeys(path for path in candidates if path.is_dir()))


def _formal_toolchain() -> tuple[Path, Path] | None:
    sby = _tool_path("sby")
    verilator = _tool_path("verilator")
    if sby is None or verilator is None:
        return None
    return sby, verilator


@unittest.skipUnless(shutil.which("verilator"), "Verilator is not installed")
class VerilatorIntegrationTests(unittest.TestCase):
    def test_real_verilator_xml_can_be_normalized_for_simple_counter(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            shutil.copyfile(FIXTURES / "rtl" / "simple_counter.sv", repo / "rtl" / "simple_counter.sv")
            (repo / "rtl" / "files.f").write_text("simple_counter.sv\n", encoding="utf-8")
            config = normalize_config(
                CLIConfig(
                    repo_root=repo,
                    work_dir=repo / ".dv-platform",
                    output_dir=repo / "generated" / "dv-platform",
                    rtl_filelists=(repo / "rtl" / "files.f",),
                    top_modules=("simple_counter",),
                )
            )
            inventory = discover_project(config)

            run_result = run_verilator_xml(config, inventory)

            stderr = run_result.stderr_log.read_text(encoding="utf-8", errors="replace")
            self.assertEqual(run_result.return_code, 0, stderr)
            self.assertIsNotNone(run_result.version)
            self.assertGreaterEqual(len(run_result.xml_files), 1)

            modules = normalize_verilator_xml(run_result.xml_files)
            facts_path = write_normalized_rtl_facts(config, modules, run_result.version)

            self.assertTrue(facts_path.is_file())
            self.assertIn("simple_counter", tuple(module.name for module in modules))


@unittest.skipUnless(shutil.which("verilator") and shutil.which("iverilog"), "Verilator and Icarus are not installed")
class PilotWorkflowIntegrationTests(unittest.TestCase):
    def test_strict_systemverilog_generation_records_real_verilator_lint(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            pilot = FIXTURES / "pilot"
            shutil.copytree(pilot / "rtl", repo / "rtl")
            shutil.copytree(pilot / "docs", repo / "docs")
            commands = (
                [
                    "--repo-root",
                    str(repo),
                    "--ci",
                    "init",
                    "--documentation-path",
                    "docs",
                    "--rtl-filelist",
                    "rtl/files.f",
                    "--top-module",
                    "pilot_top",
                    "--parameter",
                    "WIDTH=12",
                ],
                ["--repo-root", str(repo), "analyze-rtl"],
                ["--repo-root", str(repo), "index-docs"],
                ["--repo-root", str(repo), "plan", "--target", "systemverilog"],
                ["--repo-root", str(repo), "generate", "--target", "systemverilog"],
            )
            for command in commands:
                exit_code, output = _run_cli(command)
                self.assertEqual(exit_code, 0, f"{command}:\n{output}")

            provenance_paths = sorted(repo.glob("generated/**/provenance.json"))
            self.assertEqual(len(provenance_paths), 3)
            for path in provenance_paths:
                validation = json.loads(path.read_text(encoding="utf-8"))["tool_validation"]
                self.assertEqual(validation["status"], "passed")
                self.assertEqual(validation["return_code"], 0)
                self.assertEqual(validation["validator"], "verilator-systemverilog")
                self.assertNotIn(".staging-", " ".join(validation["command"]))

    def test_realistic_pilot_workflow_is_repeatable_and_ci_clean(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            pilot = FIXTURES / "pilot"
            shutil.copytree(pilot / "rtl", repo / "rtl")
            shutil.copytree(pilot / "docs", repo / "docs")

            exit_code, output = _run_cli(
                [
                    "--repo-root",
                    str(repo),
                    "--ci",
                    "init",
                    "--documentation-path",
                    "docs",
                    "--rtl-filelist",
                    "rtl/files.f",
                    "--top-module",
                    "pilot_top",
                    "--parameter",
                    "WIDTH=12",
                ]
            )
            self.assertEqual(exit_code, 0, output)
            config_path = repo / DEFAULT_CONFIG_FILENAME
            config = load_config(config_path)
            config = replace(
                config,
                simulators=(SimulatorConfig(VerificationTarget.COCOTB, "icarus", "iverilog"),),
            )
            write_config(config, config_path)

            self.assertEqual(config.parameter_overrides, ("WIDTH=12",))

            workflow = (
                ["--repo-root", str(repo), "analyze-rtl"],
                ["--repo-root", str(repo), "index-docs"],
                ["--repo-root", str(repo), "plan", "--target", "cocotb"],
                ["--repo-root", str(repo), "generate", "--target", "cocotb"],
                ["--repo-root", str(repo), "run", "--target", "cocotb", "--all"],
                ["--repo-root", str(repo), "review"],
                ["--repo-root", str(repo), "--json", "status", "--policy", "ci"],
            )
            self._assert_workflow_passes(workflow)
            facts = json.loads((repo / ".dv-platform" / "rtl-facts" / "modules.json").read_text(encoding="utf-8"))
            modules = {module["name"]: module for module in facts["modules"]}
            self.assertEqual(modules["pilot_top"]["parameter_details"][0]["default_value"], "32'hc")
            self.assertEqual(modules["stream_buffer"]["memories"][0]["depth"], 2)
            self.assertEqual(len(modules["stream_buffer"]["protocols"]), 2)
            self.assertEqual(modules["pilot_top"]["instance_details"][1]["module_name"], "stream_buffer")
            self.assertGreaterEqual(len(modules["pilot_top"]["instance_details"][1]["connections"]), 8)
            stream_summary = json.loads(
                (repo / ".dv-platform" / "runs" / "simulation" / "cocotb" / "stream_buffer" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )
            self.assertEqual(stream_summary["results"]["tests"], 2)
            self.assertEqual(stream_summary["verification_coverage"]["passed"], 11)
            first_hashes = _stable_pilot_hashes(repo)

            stale_module = repo / "generated" / "dv-platform" / "simulation" / "cocotb" / "modules" / "obsolete"
            stale_module.mkdir(parents=True)
            (stale_module / "old.py").write_text("stale\n", encoding="utf-8")
            generated_module = stale_module.parent / "event_counter"
            (generated_module / "stale.txt").write_text("stale\n", encoding="utf-8")
            stale_plan = repo / ".dv-platform" / "plans" / "modules" / "obsolete.plan.md"
            stale_plan.write_text("stale\n", encoding="utf-8")
            stale_claims = repo / ".dv-platform" / "plans" / "claims" / "obsolete"
            stale_claims.mkdir()
            (stale_claims / "claims.json").write_text("{}\n", encoding="utf-8")

            self._assert_workflow_passes(workflow)
            second_hashes = _stable_pilot_hashes(repo)

            self.assertEqual(first_hashes, second_hashes)
            self.assertFalse(stale_module.exists())
            self.assertFalse((generated_module / "stale.txt").exists())
            self.assertFalse(stale_plan.exists())
            self.assertFalse(stale_claims.exists())

    def _assert_workflow_passes(self, workflow: tuple[list[str], ...]) -> None:
        for command in workflow:
            exit_code, output = _run_cli(command)
            self.assertEqual(exit_code, 0, f"{command}:\n{output}")
            if command[-3:] == ["status", "--policy", "ci"]:
                payload = json.loads(output)
                self.assertTrue(payload["ok"])
                self.assertEqual(payload["data"]["policy"]["failures"], [])


@unittest.skipUnless(_formal_toolchain() is not None, "SymbiYosys and Verilator are not installed")
class SymbiYosysIntegrationTests(unittest.TestCase):
    def test_real_symbiyosys_proves_ready_valid_memory_stability(self) -> None:
        toolchain = _formal_toolchain()
        self.assertIsNotNone(toolchain)
        sby, verilator = toolchain or (Path("sby"), Path("verilator"))
        toolchain_path = str(sby.parent) + os.pathsep + os.environ.get("PATH", "")

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "docs").mkdir()
            shutil.copyfile(FIXTURES / "pilot" / "rtl" / "stream_buffer.sv", repo / "rtl" / "stream_buffer.sv")
            (repo / "rtl" / "files.f").write_text("stream_buffer.sv\n", encoding="utf-8")
            (repo / "docs" / "stream.md").write_text(
                "A transfer occurs when in_valid and in_ready are asserted. While out_valid is asserted and "
                "out_ready is low, out_valid and out_data remain stable.\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"PATH": toolchain_path}):
                init_exit, init_output = _run_cli(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "stream_buffer",
                        "--parameter",
                        "WIDTH=12",
                        "--documentation-path",
                        "docs",
                        "--verilator-executable",
                        str(verilator),
                    ]
                )
                self.assertEqual(init_exit, 0, init_output)

                config_path = repo / DEFAULT_CONFIG_FILENAME
                config = load_config(config_path)
                config = replace(config, formal_tools=(FormalToolConfig("symbiyosys", "sby"),))
                write_config(config, config_path)

                for command in (
                    ["--repo-root", str(repo), "analyze-rtl"],
                    ["--repo-root", str(repo), "index-docs"],
                    ["--repo-root", str(repo), "plan", "--target", "formal"],
                    ["--repo-root", str(repo), "generate", "--target", "formal"],
                    [
                        "--repo-root",
                        str(repo),
                        "run",
                        "--target",
                        "formal",
                        "--module",
                        "stream_buffer",
                        "--timeout-seconds",
                        "120",
                    ],
                ):
                    exit_code, output = _run_cli(command)
                    self.assertEqual(exit_code, 0, output + _formal_failure_context(repo, "stream_buffer"))

            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "stream_buffer"
            harness_text = (generated_dir / "formal_stream_buffer.sv").read_text(encoding="utf-8")
            summary = json.loads(
                (repo / ".dv-platform" / "runs" / "formal" / "stream_buffer" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )

            self.assertIn("reg [11:0] in_data = '0;", harness_text)
            self.assertIn("assert(out_valid);", harness_text)
            self.assertIn("assert(out_data == $past(out_data));", harness_text)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["formal_status"], "pass")

    def test_real_symbiyosys_proves_generated_simple_counter_harness(self) -> None:
        toolchain = _formal_toolchain()
        self.assertIsNotNone(toolchain)
        sby, verilator = toolchain or (Path("sby"), Path("verilator"))
        toolchain_path = str(sby.parent) + os.pathsep + os.environ.get("PATH", "")

        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl").mkdir()
            (repo / "docs").mkdir()
            shutil.copyfile(FIXTURES / "rtl" / "simple_counter.sv", repo / "rtl" / "simple_counter.sv")
            (repo / "rtl" / "files.f").write_text("simple_counter.sv\n", encoding="utf-8")
            (repo / "docs" / "counter.md").write_text(
                "rst_n clears count_o to zero. The simple_counter increments count_o when enable_i is asserted. "
                "count_o holds when enable_i is low.\n",
                encoding="utf-8",
            )

            with patch.dict(os.environ, {"PATH": toolchain_path}):
                init_exit, init_output = _run_cli(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "simple_counter",
                        "--documentation-path",
                        "docs",
                        "--verilator-executable",
                        str(verilator),
                    ]
                )
                self.assertEqual(init_exit, 0, init_output)

                config_path = repo / DEFAULT_CONFIG_FILENAME
                config = load_config(config_path)
                config = replace(config, formal_tools=(FormalToolConfig("symbiyosys", "sby"),))
                write_config(config, config_path)

                for command in (
                    ["--repo-root", str(repo), "analyze-rtl"],
                    ["--repo-root", str(repo), "index-docs"],
                    ["--repo-root", str(repo), "plan", "--target", "formal"],
                    ["--repo-root", str(repo), "generate", "--target", "formal"],
                    [
                        "--repo-root",
                        str(repo),
                        "run",
                        "--target",
                        "formal",
                        "--module",
                        "simple_counter",
                        "--timeout-seconds",
                        "120",
                    ],
                ):
                    exit_code, output = _run_cli(command)
                    self.assertEqual(exit_code, 0, output)

            generated_dir = repo / "generated" / "dv-platform" / "formal" / "modules" / "simple_counter"
            harness = generated_dir / "formal_simple_counter.sv"
            summary = json.loads(
                (repo / ".dv-platform" / "runs" / "formal" / "simple_counter" / "summary.json").read_text(
                    encoding="utf-8"
                )
            )

            harness_text = harness.read_text(encoding="utf-8")
            self.assertIn("wire [7:0] count_o;", harness_text)
            self.assertIn("assert(count_o == '0);", harness_text)
            self.assertIn("assert(count_o == $past(count_o) + 1'b1);", harness_text)
            self.assertIn("assert(count_o == $past(count_o));", harness_text)
            self.assertEqual(summary["status"], "passed")
            self.assertEqual(summary["formal_status"], "pass")
            self.assertEqual(summary["proof_method"], "k-induction")


def _stable_pilot_hashes(repo: Path) -> dict[str, str]:
    roots = (
        repo / ".dv-platform" / "rtl-facts",
        repo / ".dv-platform" / "rag-index",
        repo / ".dv-platform" / "plans",
        repo / ".dv-platform" / "review",
        repo / "generated" / "dv-platform",
    )
    hashes: dict[str, str] = {}
    for root in roots:
        if not root.is_dir():
            continue
        for path in sorted(root.rglob("*"), key=lambda item: item.as_posix()):
            if not path.is_file() or path.suffix == ".sqlite":
                continue
            hashes[str(path.relative_to(repo))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return hashes


def _formal_failure_context(repo: Path, module: str) -> str:
    run_dir = repo / ".dv-platform" / "runs" / "formal" / module
    details: list[str] = []
    for name in ("summary.json", "stdout.log", "stderr.log"):
        path = run_dir / name
        if path.is_file():
            details.append(f"\n--- {name} ---\n{path.read_text(encoding='utf-8', errors='replace')}")
    return "".join(details)


def _run_cli(argv: list[str]) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(argv)
    return exit_code, output.getvalue()


if __name__ == "__main__":
    unittest.main()
