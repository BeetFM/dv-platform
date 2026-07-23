import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.core.models import EvidenceKind
from dv_platform.enterprise.requirements import (
    RequirementsImportError,
    RequirementsManifestImporter,
)


class RequirementsManifestImporterTests(TestCase):
    def test_imports_governed_requirement_baseline(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "baseline.dvreq.json"
            path.write_text(json.dumps(_document()), encoding="utf-8")

            result = RequirementsManifestImporter().import_requirements(path, strict=True)

        self.assertEqual(result.baseline_id, "BASELINE-42")
        self.assertEqual(len(result.requirements), 2)
        child = result.requirements[1]
        self.assertEqual(child.parent_ids, ("REQ-1",))
        self.assertEqual(child.requirement.confidence, "governed")
        self.assertEqual(
            child.requirement.evidence_refs[0].kind,
            EvidenceKind.REQUIREMENTS_EXPORT,
        )

    def test_rejects_unapproved_strict_duplicate_and_missing_parent(self) -> None:
        cases: list[tuple[dict, str]] = []
        unapproved = _document()
        unapproved["requirements"][0]["status"] = "draft"
        cases.append((unapproved, "rejects status"))
        duplicate = _document()
        duplicate["requirements"][1]["requirement_id"] = "REQ-1"
        cases.append((duplicate, "duplicate requirement_id"))
        missing = _document()
        missing["requirements"][1]["parent_ids"] = ["REQ-MISSING"]
        cases.append((missing, "missing parents"))

        with TemporaryDirectory() as directory:
            root = Path(directory)
            for index, (document, message) in enumerate(cases):
                path = root / f"case-{index}.requirements.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(index=index), self.assertRaisesRegex(RequirementsImportError, message):
                    RequirementsManifestImporter().import_requirements(path, strict=index == 0)


def _document() -> dict:
    return {
        "schema_version": 1,
        "producer": "enterprise-alm",
        "baseline_id": "BASELINE-42",
        "exported_at": "2026-07-19T14:00:00Z",
        "requirements": [
            {
                "requirement_id": "REQ-1",
                "scope": "bridge",
                "statement": "The bridge shall reset ready low.",
                "category": "reset",
                "signals": ["ready", "rst_n"],
                "expected_value": "0",
                "condition": "!rst_n",
                "status": "approved",
                "verification_method": "formal",
                "parent_ids": [],
                "tags": ["safety"],
            },
            {
                "requirement_id": "REQ-2",
                "scope": "bridge",
                "statement": "The bridge shall transfer accepted requests.",
                "status": "released",
                "verification_method": "simulation",
                "parent_ids": ["REQ-1"],
                "tags": [],
            },
        ],
    }
