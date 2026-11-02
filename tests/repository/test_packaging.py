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

    def test_hosted_quality_job_checks_the_current_workflow(self) -> None:
        workflow = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
        self.assertIn("scripts.checks.repository_contracts", workflow)
        self.assertIn("scripts.checks.branch_coverage", workflow)
        self.assertIn("uv build --wheel --project enterprise", workflow)

    def test_module_entry_point_displays_help(self) -> None:
        completed = subprocess.run(
            [sys.executable, "-m", "dv_platform", "--help"],
            cwd=ROOT,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(completed.returncode, 0)
        self.assertIn("context-optimize", completed.stdout)
        self.assertIn("status", completed.stdout)


if __name__ == "__main__":
    unittest.main()
