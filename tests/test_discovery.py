from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.discovery import parse_filelist


class DiscoveryTests(unittest.TestCase):
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


if __name__ == "__main__":
    unittest.main()
