import subprocess
import tarfile
import unittest
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

from tests.support.paths import REPOSITORY_ROOT


class ProductPackagingTests(unittest.TestCase):
    def test_free_and_enterprise_wheels_are_separate_and_exactly_versioned(self):
        with TemporaryDirectory() as directory:
            output = Path(directory)
            subprocess.run(
                ("uv", "build", "--out-dir", str(output / "free")),
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                timeout=120,
            )
            subprocess.run(
                ("uv", "build", "--wheel", "--project", "enterprise", "--out-dir", str(output / "enterprise")),
                cwd=REPOSITORY_ROOT,
                check=True,
                capture_output=True,
                timeout=120,
            )
            free_wheel = next((output / "free").glob("*.whl"))
            free_sdist = next((output / "free").glob("*.tar.gz"))
            enterprise_wheel = next((output / "enterprise").glob("*.whl"))
            with zipfile.ZipFile(free_wheel) as archive:
                free_names = set(archive.namelist())
                free_entries = archive.read("dv_platform-1.0.0rc3.dist-info/entry_points.txt").decode()
            with zipfile.ZipFile(enterprise_wheel) as archive:
                enterprise_names = set(archive.namelist())
                metadata = archive.read("dv_platform_enterprise-1.0.0rc3.dist-info/METADATA").decode()
            with tarfile.open(free_sdist) as archive:
                free_sdist_names = set(archive.getnames())

        private_free_paths = {
            name
            for name in free_names
            if name.startswith("dv_platform/enterprise/") and not name.endswith("__init__.py")
        }
        self.assertEqual(private_free_paths, set())
        self.assertNotIn("dv-enterprise", free_entries)
        self.assertFalse(any(name.startswith("dv_platform_enterprise_impl/") for name in free_names))
        self.assertFalse(any("/src/dv_platform/enterprise/" in name for name in free_sdist_names))
        enterprise_sdist_paths = {
            name for name in free_sdist_names if "/enterprise/" in name and not name.endswith("/__init__.py")
        }
        self.assertEqual(enterprise_sdist_paths, set())
        self.assertTrue(any(name.startswith("dv_platform_enterprise_impl/") for name in enterprise_names))
        self.assertFalse(any(name.startswith("dv_platform/enterprise/") for name in enterprise_names))
        self.assertIn("Requires-Dist: dv-platform==1.0.0rc3", metadata)


if __name__ == "__main__":
    unittest.main()
