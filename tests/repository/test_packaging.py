import subprocess
import sys
import tomllib
import unittest

import dv_platform
from tests.support.paths import REPOSITORY_ROOT

ROOT = REPOSITORY_ROOT


class PackagingTests(unittest.TestCase):
    def test_package_version_matches_project_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(dv_platform.__version__, metadata["project"]["version"])

    def test_project_defines_console_script_entry_point(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["scripts"]["dv-platform"], "dv_platform.cli:main")

    def test_project_metadata_does_not_use_placeholder_urls(self) -> None:
        metadata_text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")

        self.assertNotIn("example.invalid", metadata_text)

    def test_hosted_quality_job_makes_pinned_formal_pilot_mandatory(self) -> None:
        workflow = (ROOT / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

        self.assertIn("fea6e467d067b3ea84b6b5ac08cd48beb59f0d42", workflow)
        self.assertIn("yosys z3", workflow)
        self.assertIn("tests.integration.test_verilator_integration.SymbiYosysIntegrationTests", workflow)

    def test_module_entry_point_displays_help(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "dv_platform", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("Local agentic RTL verification generation CLI", completed.stdout)


if __name__ == "__main__":
    unittest.main()
