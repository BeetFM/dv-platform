import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.checks.repository_contracts import (
    ROOT,
    check_capability_ledger,
    check_capability_matrix,
    check_cli_examples,
    check_document_consolidation,
    check_internal_links,
    check_schema_versions,
)


class RepositoryContractTests(TestCase):
    def test_documentation_and_schema_contracts(self) -> None:
        self.assertEqual(check_internal_links(), [])
        self.assertEqual(check_document_consolidation(), [])
        self.assertEqual(check_cli_examples(), [])
        self.assertEqual(check_schema_versions(), [])
        self.assertEqual(check_capability_matrix(), [])
        self.assertEqual(check_capability_ledger(), [])

    def test_capability_ledger_rejects_contradictory_state(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qualification" / "policies").mkdir(parents=True)
            (root / "docs").mkdir()
            shutil.copy(ROOT / "docs" / "verification.md", root / "docs" / "verification.md")
            shutil.copy(ROOT / "docs" / "architecture.md", root / "docs" / "architecture.md")
            ledger = json.loads((ROOT / "qualification" / "policies" / "capability-ledger-v1.json").read_text())
            ledger["cells"][0]["state"] = "supported"
            path = root / "qualification" / "policies" / "capability-ledger-v1.json"
            path.write_text(json.dumps(ledger), encoding="utf-8")
            self.assertTrue(
                any(
                    "supported cell lacks passing evidence identity" in error for error in check_capability_ledger(root)
                )
            )

    def test_capability_ledger_rejects_grouped_and_unknown_cells(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qualification" / "policies").mkdir(parents=True)
            (root / "docs").mkdir()
            shutil.copy(ROOT / "docs" / "verification.md", root / "docs" / "verification.md")
            ledger = json.loads((ROOT / "qualification" / "policies" / "capability-ledger-v1.json").read_text())
            ledger["cells"][0]["target"] = "cocotb|formal"
            path = root / "qualification" / "policies" / "capability-ledger-v1.json"
            path.write_text(json.dumps(ledger), encoding="utf-8")
            errors = check_capability_ledger(root)
            self.assertTrue(any("unknown role or target cell" in error for error in errors))
