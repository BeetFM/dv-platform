from unittest import TestCase

from scripts.release.publication import PublicationConflict, decide_publication, verify_reinstall


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
