from pathlib import Path
import shutil
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.discovery import discover_project
from dv_platform.analysis.rtl import normalize_verilator_xml, run_verilator_xml, write_normalized_rtl_facts
from dv_platform.core.config import normalize_config
from dv_platform.core.models import CLIConfig


FIXTURES = Path(__file__).parent / "fixtures"


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


if __name__ == "__main__":
    unittest.main()
