import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.discovery import build_verilator_dry_run_command, discover_project, parse_filelist
from dv_platform.core.config import default_config


class DiscoveryTests(unittest.TestCase):
    def test_repository_walk_excludes_configured_work_and_output_trees(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            (repo / "rtl").mkdir()
            (repo / "rtl" / "real.sv").write_text("module real; endmodule\n", encoding="utf-8")
            generated = config.output_dir / "simulation" / "systemverilog" / "modules" / "real"
            generated.mkdir(parents=True)
            (generated / "tb_real.sv").write_text("module tb_real; endmodule\n", encoding="utf-8")
            config.work_dir.mkdir(parents=True)
            (config.work_dir / "cached.v").write_text("module cached; endmodule\n", encoding="utf-8")

            inventory = discover_project(config)

            self.assertEqual(tuple(item.path for item in inventory.hdl_files), (repo / "rtl" / "real.sv",))

    def test_parse_filelist_supports_nested_lists_and_split_plus_flags(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "rtl" / "include").mkdir(parents=True)
            (repo / "rtl" / "vip").mkdir()
            (repo / "rtl" / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            (repo / "rtl" / "helper.v").write_text("module helper; endmodule\n", encoding="utf-8")
            (repo / "rtl" / "nested.f").write_text(
                "+incdir+include+vip\n+define+SIM=1+ASSERT_ON\n-v helper.v\n",
                encoding="utf-8",
            )
            (repo / "rtl" / "files.f").write_text("-f nested.f\ntop.sv\n", encoding="utf-8")

            inventory = parse_filelist(repo / "rtl" / "files.f", repo)

            self.assertEqual(
                tuple(hdl_file.path for hdl_file in inventory.hdl_files),
                (repo / "rtl" / "helper.v", repo / "rtl" / "top.sv"),
            )
            self.assertEqual(
                inventory.include_paths,
                (repo / "rtl" / "include", repo / "rtl" / "vip"),
            )
            self.assertEqual(inventory.defines, ("SIM=1", "ASSERT_ON"))

    def test_parse_filelist_rejects_recursive_includes(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "files.f").write_text("-f nested.f\n", encoding="utf-8")
            (repo / "nested.f").write_text("-f files.f\n", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "Recursive RTL file list"):
                parse_filelist(repo / "files.f", repo)

    def test_verilator_command_applies_top_parameter_overrides(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            config = replace(
                default_config(repo),
                top_modules=("top",),
                parameter_overrides=("WIDTH=12", "DEPTH=2"),
            )
            inventory = discover_project(config)

            command = build_verilator_dry_run_command(config, inventory)

            self.assertIn("-GWIDTH=12", command)
            self.assertIn("-GDEPTH=2", command)

    def test_verilator_command_applies_one_sweep_point(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            (repo / "top.sv").write_text("module top; endmodule\n", encoding="utf-8")
            config = replace(
                default_config(repo),
                top_modules=("top",),
                parameter_overrides=("WIDTH=16", "DEPTH=4"),
            )
            command = build_verilator_dry_run_command(config, discover_project(config))

            self.assertEqual(command.count("-GWIDTH=16"), 1)
            self.assertEqual(command.count("-GDEPTH=4"), 1)


if __name__ == "__main__":
    unittest.main()
