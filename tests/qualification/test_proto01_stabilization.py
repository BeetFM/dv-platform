import json
import unittest
from pathlib import Path

from scripts.qualification.stabilize_proto01_evidence import MANIFEST_PATH, verify_manifest

ROOT = Path(__file__).resolve().parents[2]


class Proto01StabilizationTests(unittest.TestCase):
    def test_distributable_records_match_retention_manifest(self) -> None:
        verify_manifest(require_artifacts=False)
        manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
        self.assertEqual(manifest["ticket"], "PROTO-01")
        self.assertEqual(manifest["record_count"], 35)
        self.assertEqual(len(manifest["records"]), 35)
        self.assertEqual(len({item["sha256"] for item in manifest["records"]}), 35)


if __name__ == "__main__":
    unittest.main()
