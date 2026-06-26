import subprocess
import sys
import tomllib
from pathlib import Path
import unittest

import dv_platform


ROOT = Path(__file__).resolve().parents[1]


class PackagingTests(unittest.TestCase):
    def test_package_version_matches_project_metadata(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(dv_platform.__version__, metadata["project"]["version"])

    def test_project_defines_console_script_entry_point(self) -> None:
        metadata = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))

        self.assertEqual(metadata["project"]["scripts"]["dv-platform"], "dv_platform.cli:main")

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
