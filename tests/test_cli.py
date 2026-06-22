import io
import json
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.cli import build_parser, config_from_args, main
from dv_platform.core.config import DEFAULT_CONFIG_FILENAME, load_config


class CLITests(unittest.TestCase):
    def test_config_defaults_to_local_only_workflow(self) -> None:
        parser = build_parser()
        args = parser.parse_args(["--repo-root", "repo", "--work-dir", "work", "plan"])

        config = config_from_args(args)

        expected_root = Path("repo").resolve(strict=False)
        self.assertEqual(config.repo_root, expected_root)
        self.assertEqual(config.work_dir, expected_root / "work")
        self.assertEqual(config.retrieval_index_dir, expected_root / "work" / "rag-index")
        self.assertFalse(config.allow_network)

    def test_command_prints_local_paths(self) -> None:
        output = io.StringIO()

        with redirect_stdout(output):
            exit_code = main(
                [
                    "--repo-root",
                    "repo",
                    "--work-dir",
                    "work",
                    "--output-dir",
                    "out",
                    "plan",
                ]
            )

        self.assertEqual(exit_code, 0)
        text = output.getvalue()
        expected_root = Path("repo").resolve(strict=False)
        self.assertIn("command=plan", text)
        self.assertIn(f"repo_root={expected_root}", text)
        self.assertIn(f"work_dir={expected_root / 'work'}", text)
        self.assertIn(f"output_dir={expected_root / 'out'}", text)
        self.assertIn("allow_network=False", text)

    def test_init_writes_loadable_config(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config_path = repo / DEFAULT_CONFIG_FILENAME

            with redirect_stdout(io.StringIO()):
                exit_code = main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--documentation-path",
                        "specs",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--include-path",
                        "rtl/include",
                        "--define",
                        "SYNTHESIS=0",
                        "--top-module",
                        "top",
                    ]
                )

            self.assertEqual(exit_code, 0)
            config = load_config(config_path)
            self.assertEqual(config.documentation_paths, (repo / "specs",))
            self.assertEqual(config.rtl_filelists, (repo / "rtl" / "files.f",))
            self.assertEqual(config.include_paths, (repo / "rtl" / "include",))
            self.assertEqual(config.defines, ("SYNTHESIS=0",))
            self.assertEqual(config.top_modules, ("top",))

    def test_analyze_rtl_dry_run_discovers_sources_and_writes_manifest(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl" / "include").mkdir(parents=True)
            (repo / "docs").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            (repo / "docs" / "top.md").write_text("# Top\n", encoding="utf-8")
            (repo / "rtl" / "files.f").write_text(
                "+incdir+include\n+define+SIM=1\ntop.sv\n",
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                main(
                    [
                        "--repo-root",
                        str(repo),
                        "init",
                        "--documentation-path",
                        "docs",
                        "--rtl-filelist",
                        "rtl/files.f",
                        "--top-module",
                        "top",
                    ]
                )

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(repo), "analyze-rtl", "--dry-run"])

            self.assertEqual(exit_code, 0)
            text = output.getvalue()
            manifest_path = repo / ".dv-platform" / "project-manifest.json"
            self.assertIn("hdl_files=1", text)
            self.assertIn("documentation_files=1", text)
            self.assertIn(f"manifest={manifest_path}", text)

            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            self.assertEqual(manifest["hdl_files"][0]["path"], str(repo / "rtl" / "top.sv"))
            self.assertEqual(manifest["hdl_files"][0]["language"], "systemverilog")
            self.assertEqual(manifest["documentation_files"], [str(repo / "docs" / "top.md")])
            self.assertEqual(manifest["include_paths"], [str(repo / "rtl" / "include")])
            self.assertEqual(manifest["defines"], ["SIM=1"])
            self.assertIn("--top-module", manifest["verilator_command"])


if __name__ == "__main__":
    unittest.main()
