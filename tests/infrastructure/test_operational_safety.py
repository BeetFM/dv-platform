import io
import json
import os
import sqlite3
from contextlib import redirect_stdout
from dataclasses import replace
from datetime import UTC, date, datetime
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.cli import main
from dv_platform.core.config import default_config
from dv_platform.core.io import backup_sqlite_database, restore_sqlite_database, sqlite_integrity_check
from dv_platform.core.operations import verify_project_backup
from dv_platform.core.security import purge_retained_files


class OperationalSafetyTests(TestCase):
    def test_sqlite_backup_and_restore_are_integrity_checked(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "plans.sqlite"
            with sqlite3.connect(source) as database:
                database.execute("CREATE TABLE plans (module TEXT PRIMARY KEY)")
                database.execute("INSERT INTO plans VALUES ('bridge')")

            backup = root / "backups" / "plans.sqlite"
            restored = root / "restored" / "plans.sqlite"
            backup_sqlite_database(source, backup)
            backup_sqlite_database(backup, restored)

            with sqlite3.connect(restored) as database:
                self.assertEqual(database.execute("PRAGMA integrity_check").fetchone(), ("ok",))
                self.assertEqual(database.execute("SELECT module FROM plans").fetchall(), [("bridge",)])
            with self.assertRaises(FileExistsError):
                backup_sqlite_database(source, backup)
            with self.assertRaisesRegex(ValueError, "regular file"):
                backup_sqlite_database(root / "missing.sqlite", root / "missing-backup.sqlite")

            corrupt = root / "corrupt.sqlite"
            corrupt.write_text("not sqlite", encoding="utf-8")
            with self.assertRaises(sqlite3.DatabaseError):
                sqlite_integrity_check(corrupt)
            with self.assertRaises(sqlite3.DatabaseError):
                restore_sqlite_database(corrupt, root / "corrupt-restored.sqlite")

    def test_retention_purge_is_dry_run_by_default_and_refuses_symlinks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(default_config(root), retention_days=30)
            expired = config.work_dir / "logs" / "expired.log"
            current = config.work_dir / "logs" / "current.log"
            expired.parent.mkdir(parents=True)
            expired.write_text("old", encoding="utf-8")
            current.write_text("new", encoding="utf-8")
            os.utime(expired, (0, 0))
            current_timestamp = datetime(2026, 7, 20, tzinfo=UTC).timestamp()
            os.utime(current, (current_timestamp, current_timestamp))

            selected = purge_retained_files(config, as_of=date(2026, 7, 21))
            self.assertEqual(selected, (expired,))
            self.assertTrue(expired.exists())
            purge_retained_files(config, as_of=date(2026, 7, 21), apply=True)
            self.assertFalse(expired.exists())
            self.assertTrue(current.exists())

            target = root / "outside.log"
            target.write_text("outside", encoding="utf-8")
            link = config.work_dir / "logs" / "escape.log"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "refuses symbolic links"):
                purge_retained_files(config, as_of=date(2026, 7, 21), apply=True)
            self.assertTrue(target.exists())

    def test_purge_cli_has_stable_json_dry_run_and_apply(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            expired = root / ".dv-platform" / "logs" / "expired.log"
            expired.parent.mkdir(parents=True)
            expired.write_text("old", encoding="utf-8")
            os.utime(expired, (0, 0))

            output = io.StringIO()
            with redirect_stdout(output):
                exit_code = main(["--repo-root", str(root), "--json", "purge", "--as-of", "2026-07-21"])

            self.assertEqual(exit_code, 0)
            payload = json.loads(output.getvalue())
            self.assertFalse(payload["data"]["apply"])
            self.assertEqual(payload["data"]["files"], [str(expired)])
            self.assertTrue(expired.exists())

            with redirect_stdout(io.StringIO()):
                exit_code = main(["--repo-root", str(root), "--json", "purge", "--as-of", "2026-07-21", "--apply"])
            self.assertEqual(exit_code, 0)
            self.assertFalse(expired.exists())

    def test_backup_and_migrate_cli_are_dry_run_then_verified_apply(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            state = root / ".dv-platform" / "plans" / "top.json"
            state.parent.mkdir(parents=True)
            state.write_text(json.dumps({"schema_version": 18, "module": "top", "targets": []}), encoding="utf-8")
            output = io.StringIO()
            backup = root / "backup"
            with redirect_stdout(output):
                result = main(["--repo-root", str(root), "--json", "backup", "--output", str(backup)])
            self.assertEqual(result, 0)
            self.assertFalse(backup.exists())

            with redirect_stdout(io.StringIO()):
                result = main(["--repo-root", str(root), "--json", "backup", "--output", str(backup), "--apply"])
            self.assertEqual(result, 0)
            verify_project_backup(backup)

            with redirect_stdout(io.StringIO()):
                result = main(["--repo-root", str(root), "--json", "migrate", "--backup", str(backup), "--apply"])
            self.assertEqual(result, 0)
            self.assertEqual(json.loads(state.read_text(encoding="utf-8"))["schema_version"], 19)

    def test_governed_destruction_requires_backup_and_honors_legal_hold(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / ".dv-platform" / "runs"
            target.mkdir(parents=True)
            evidence = target / "run.json"
            evidence.write_text("{}", encoding="utf-8")
            durable = root / ".dv-platform" / "plans" / "plan.json"
            durable.parent.mkdir(parents=True)
            durable.write_text(json.dumps({"schema_version": 18, "module": "top", "targets": []}), encoding="utf-8")
            backup = root / "recovery"
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(["--repo-root", str(root), "backup", "--output", str(backup), "--apply"]), 0)
            holds = root / "holds.json"
            holds.write_text(json.dumps({"schema_version": 1, "holds": []}), encoding="utf-8")
            command = [
                "--repo-root",
                str(root),
                "--json",
                "destroy",
                "--retention-class",
                "run-evidence",
                "--target",
                str(target),
                "--authorization",
                "CHG-123",
                "--legal-holds",
                str(holds),
                "--recovery-backup",
                str(backup),
            ]
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main(command), 0)
            self.assertTrue(evidence.exists())
            holds.write_text(
                json.dumps(
                    {"schema_version": 1, "holds": [{"retention_class": "run-evidence", "target": "*", "active": True}]}
                ),
                encoding="utf-8",
            )
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([*command, "--apply"]), 2)
            self.assertTrue(evidence.exists())
            holds.write_text(json.dumps({"schema_version": 1, "holds": []}), encoding="utf-8")
            with redirect_stdout(io.StringIO()):
                self.assertEqual(main([*command, "--apply"]), 0)
            self.assertFalse(target.exists())
