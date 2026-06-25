import io
import json
import os
from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from unittest.mock import patch

from dv_platform.analysis.discovery import discover_project
from dv_platform.analysis.rtl import normalize_verilator_xml, run_verilator_xml, write_normalized_rtl_facts
from dv_platform.cli import main
from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, load_config, normalize_config, write_config
from dv_platform.core.models import CLIConfig, FormalToolConfig


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


@unittest.skipUnless(_formal_toolchain() is not None, "SymbiYosys and Verilator are not installed")
class SymbiYosysIntegrationTests(unittest.TestCase):
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


def _run_cli(argv: list[str]) -> tuple[int, str]:
    output = io.StringIO()
    with redirect_stdout(output):
        exit_code = main(argv)
    return exit_code, output.getvalue()


if __name__ == "__main__":
    unittest.main()
