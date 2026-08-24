from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.release.publication import PublicationConflict, decide_publication, subject_digests, verify_reinstall


class PublicationTests(TestCase):
    def test_missing_uploads_matching_is_noop_and_different_is_conflict(self) -> None:
        expected = {"package.whl": "a" * 64, "package.tar.gz": "b" * 64}
        self.assertEqual(decide_publication(expected, None).action, "upload")
        self.assertEqual(decide_publication(expected, expected).action, "noop")
        with self.assertRaisesRegex(PublicationConflict, "different subjects"):
            decide_publication(expected, {"package.whl": "c" * 64, "package.tar.gz": "b" * 64})

    def test_reinstall_requires_exact_subjects(self) -> None:
        expected = {"package.whl": "a" * 64}
        verify_reinstall(expected, expected)
        with self.assertRaisesRegex(PublicationConflict, "reinstalled"):
            verify_reinstall(expected, {"package.whl": "b" * 64})

    def test_package_preflight_subjects_are_isolated(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "dv_platform-1.0.0rc3-py3-none-any.whl").write_bytes(b"free")
            (root / "dv_platform_enterprise-1.0.0rc3-py3-none-any.whl").write_bytes(b"enterprise")
            free = subject_digests(root, "dv-platform", "1.0.0rc3")
            enterprise = subject_digests(root, "dv-platform-enterprise", "1.0.0rc3")
        self.assertEqual(tuple(free), ("dv_platform-1.0.0rc3-py3-none-any.whl",))
        self.assertEqual(tuple(enterprise), ("dv_platform_enterprise-1.0.0rc3-py3-none-any.whl",))
