import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from scripts.checks.repository_contracts import (
    ROOT,
    _progress_transition_errors,
    check_capability_ledger,
    check_capability_matrix,
    check_cli_examples,
    check_document_catalog,
    check_document_consolidation,
    check_internal_links,
    check_local_task_audit,
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
        self.assertEqual(check_document_catalog(), [])
        self.assertEqual(check_local_task_audit(), [])

    def test_document_catalog_and_local_audit_fail_closed(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copytree(ROOT / "docs", root / "docs")
            shutil.copytree(ROOT / "qualification", root / "qualification")
            for name in ("README.md", "SECURITY.md", "CHANGELOG.md", "THIRD_PARTY_NOTICES.md", "progress.md"):
                shutil.copy(ROOT / name, root / name)
            for name in ("src", "tests", "scripts", "schemas", ".github"):
                (root / name).symlink_to(ROOT / name, target_is_directory=True)

            catalog_path = root / "qualification/policies/document-catalog-v1.json"
            catalog = json.loads(catalog_path.read_text(encoding="utf-8"))
            catalog["source_sections"].pop()
            catalog["documents"][0].pop("scope")
            catalog["documents"][0]["authority"] = "changed-authority"
            catalog_path.write_text(json.dumps(catalog), encoding="utf-8")
            errors = check_document_catalog(root)
            self.assertTrue(any("all 70 consolidated source sections" in error for error in errors))
            self.assertTrue(any("metadata is not closed" in error for error in errors))
            self.assertTrue(any("generated document catalog is stale" in error for error in errors))

            audit_path = root / "qualification/policies/local-task-audit-v1.json"
            audit = json.loads(audit_path.read_text(encoding="utf-8"))
            audit["tasks"].pop()
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            errors = check_local_task_audit(root)
            self.assertTrue(any("every current roadmap ticket" in error for error in errors))

            audit = json.loads((ROOT / "qualification/policies/local-task-audit-v1.json").read_text())
            audit["tasks"][0]["local_work_state"] = "pending_local"
            audit_path.write_text(json.dumps(audit), encoding="utf-8")
            self.assertTrue(any("unfinished repository-owned work" in error for error in check_local_task_audit(root)))

    def test_command_validation_handles_env_pipeline_scripts_and_negative_examples(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "scripts").mkdir()
            (root / "scripts/check.py").write_text("raise SystemExit(0)\n", encoding="utf-8")
            (root / "docs/commands.md").write_text(
                """# Commands

```bash
CI=1 uv run dv-platform --repo-root /tmp/demo status --policy ci | tee status.log
uv run python scripts/check.py > result.log
# expected-invalid
dv-platform status --definitely-not-a-real-option
```
""",
                encoding="utf-8",
            )
            self.assertEqual(check_cli_examples(root), [])

            (root / "docs/commands.md").write_text(
                """# Commands

```bash
uv run python scripts/missing.py
```
""",
                encoding="utf-8",
            )
            self.assertTrue(any("missing public script" in error for error in check_cli_examples(root)))

    def test_internal_links_use_github_style_repeated_and_unicode_anchors(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "docs").mkdir()
            (root / "docs/anchors.md").write_text(
                """# Résumé & Über

## Repeated heading

## Repeated heading

[Unicode](#résumé-über)
[Repeated](#repeated-heading-1)
""",
                encoding="utf-8",
            )
            self.assertEqual(check_internal_links(root), [])

            (root / "docs/anchors.md").write_text(
                "# Existing\n\n[Missing](#not-present)\n",
                encoding="utf-8",
            )
            self.assertTrue(any("broken anchor" in error for error in check_internal_links(root)))

    def test_progress_transitions_reject_ordering_duplicates_and_missing_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "evidence.txt").write_text("ok\n", encoding="utf-8")
            progress = {
                "schema_version": 1,
                "transitions": [
                    {
                        "ticket": "DOC-03",
                        "sequence": 2,
                        "from": "in_progress",
                        "to": "closed",
                        "date": "2026-07-30",
                        "evidence": ["missing.txt"],
                    },
                    {
                        "ticket": "DOC-03",
                        "sequence": 2,
                        "from": "closed",
                        "to": "regressed",
                        "date": "bad-date",
                        "evidence": ["evidence.txt"],
                    },
                ],
            }
            errors = _progress_transition_errors(progress, root)
            self.assertTrue(any("ordering is invalid" in error for error in errors))
            self.assertTrue(any("sequence is duplicated" in error for error in errors))
            self.assertTrue(any("evidence is missing" in error for error in errors))

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
