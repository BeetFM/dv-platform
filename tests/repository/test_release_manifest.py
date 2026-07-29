import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.release.manifest import ReleaseManifestError, create_manifest, verify_manifest


class ReleaseManifestTests(TestCase):
    def test_manifest_binds_build_subjects_and_checkout(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.com")
            self._git(root, "config", "user.name", "Test")
            (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n', encoding="utf-8")
            (root / "uv.lock").write_text("lock\n", encoding="utf-8")
            workflow = root / ".github" / "workflows"
            workflow.mkdir(parents=True)
            (workflow / "release.yml").write_text("workflow\n", encoding="utf-8")
            dist = root / "dist"
            dist.mkdir()
            (dist / "dv_platform-0.1.0-py3-none-any.whl").write_bytes(b"wheel")
            (dist / "dv_platform-0.1.0.tar.gz").write_bytes(b"sdist")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "release")
            manifest = dist / "release-manifest.json"
            payload = create_manifest(dist, root, manifest)
            self.assertEqual(verify_manifest(manifest, dist, root=root, expected_commit=payload["commit"]), payload)
            (dist / "dv_platform-0.1.0-py3-none-any.whl").write_bytes(b"changed")
            with self.assertRaisesRegex(ReleaseManifestError, "subjects differ"):
                verify_manifest(manifest, dist, root=root, expected_commit=payload["commit"])

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        return subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True).stdout.strip()
