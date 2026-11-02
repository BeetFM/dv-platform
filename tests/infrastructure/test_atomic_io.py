from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.infrastructure.io import atomic_write_text


class AtomicWriteTests(TestCase):
    def test_failed_replace_preserves_previous_content_and_removes_temporary_file(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "evidence.json"
            target.write_text("original")
            with patch("dv_platform.infrastructure.io.os.replace", side_effect=OSError("fixture failure")):
                with self.assertRaises(OSError):
                    atomic_write_text(target, "candidate")
            self.assertEqual(target.read_text(), "original")
            self.assertEqual(list(root.iterdir()), [target])
