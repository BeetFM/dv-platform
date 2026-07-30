import subprocess
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.release.release_policy import ReleasePolicyError, resolve_release, verify_exact_tag


class ReleasePolicyTests(TestCase):
    def test_resolves_every_supported_channel(self) -> None:
        expected = {
            "v0.1.0": ("development", 10, False),
            "v0.2.0a1": ("alpha", 10, False),
            "v0.2.0b1": ("beta", 10, False),
            "v1.0.0rc3": ("rc", 12, True),
            "v1.0.0": ("ga", 13, True),
            "v1.0.1": ("patch", 13, True),
        }
        for tag, values in expected.items():
            with self.subTest(tag=tag):
                decision = resolve_release(tag, tag[1:])
                self.assertEqual((decision.channel, decision.minimum_stage, decision.publish), values)

    def test_rejects_unsupported_or_mismatched_versions(self) -> None:
        for tag, version in (
            ("1.0.0", "1.0.0"),
            ("v1.0.0.post1", "1.0.0.post1"),
            ("v1.0.0", "0.1.0"),
            ("v01.0.0", "01.0.0"),
        ):
            with self.subTest(tag=tag):
                with self.assertRaises(ReleasePolicyError):
                    resolve_release(tag, version)

    def test_exact_tag_verification_rejects_wrong_sha_and_accepts_target(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self._git(root, "init", "-q")
            self._git(root, "config", "user.email", "test@example.com")
            self._git(root, "config", "user.name", "Test")
            (root / "file").write_text("content", encoding="utf-8")
            self._git(root, "add", ".")
            self._git(root, "commit", "-qm", "release")
            commit = self._git(root, "rev-parse", "HEAD")
            self._git(root, "tag", "v0.1.0")
            self.assertEqual(verify_exact_tag(root, "v0.1.0", commit), commit)
            with self.assertRaisesRegex(ReleasePolicyError, "target mismatch"):
                verify_exact_tag(root, "v0.1.0", "a" * 40)

    @staticmethod
    def _git(root: Path, *args: str) -> str:
        return subprocess.run(("git", *args), cwd=root, check=True, capture_output=True, text=True).stdout.strip()
