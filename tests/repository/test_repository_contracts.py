import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from scripts.checks.compatibility import compare, fingerprints
from scripts.checks.repository_contracts import check_evidence, check_internal_links, check_workflow


class RepositoryContractTests(TestCase):
    def test_link_check_detects_missing_target_and_anchor(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("# Title\n[bad](missing.md)\n[anchor](#absent)\n")
            errors = check_internal_links(root)
            self.assertEqual(len(errors), 2)

    def test_private_evidence_is_optional_for_public_checkout_checks(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "README.md").write_text("[local evidence](qualification/evidence/PHYS-01/local.json)\n")
            for name in ("AGENTS.md", "docs/README.md", "docs/verification.md", "src/dv_platform/physical_design.tcl"):
                path = root / name
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text("")
            self.assertEqual(check_internal_links(root), [])
            with patch("scripts.checks.repository_contracts.ROOT", root):
                self.assertEqual(check_workflow(), [])
            self.assertEqual(check_evidence(root), [])
            self.assertIn(
                "missing local qualification evidence manifests", check_evidence(root, require_artifacts=True)
            )

    def test_evidence_check_rejects_changes_and_path_escapes(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "qualification/evidence/PHYS-01"
            evidence.mkdir(parents=True)
            asset = root / "asset.txt"
            asset.write_text("original")
            record = {"artifacts": [{"path": "asset.txt", "sha256": hashlib.sha256(asset.read_bytes()).hexdigest()}]}
            manifest = evidence / "local.json"
            manifest.write_text(json.dumps(record))
            with patch.object(Path, "read_bytes", side_effect=AssertionError("artifact must be streamed")):
                self.assertEqual(check_evidence(root), [])
            asset.write_text("changed")
            self.assertIn("changed artifact", check_evidence(root)[0])
            record["artifacts"][0]["path"] = "../outside"
            manifest.write_text(json.dumps(record))
            self.assertIn("unsafe artifact", check_evidence(root)[0])

    def test_secret_scan_includes_new_files_and_ignores_local_environment_files(self):
        import subprocess
        from contextlib import redirect_stdout
        from io import StringIO
        from unittest.mock import patch

        from scripts.checks import secrets

        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "--quiet", str(root)), check=True, capture_output=True)
            (root / ".gitignore").write_text(".env\n")
            token = "sk-" + "a" * 48
            (root / ".env").write_text(token)
            source = root / "new.py"
            source.write_text(token)
            with patch.object(secrets, "ROOT", root), redirect_stdout(StringIO()):
                self.assertEqual(secrets.main(), 1)
                source.unlink()
                self.assertEqual(secrets.main(), 0)

    def test_clean_checkout_manifest_checks_and_required_local_artifact_checks_are_distinct(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = root / "qualification/evidence/PHYS-01"
            evidence.mkdir(parents=True)
            manifest = evidence / "local.json"
            manifest.write_text(json.dumps({"artifacts": [{"path": "missing.txt", "sha256": "a" * 64}]}))
            self.assertEqual(check_evidence(root), [])
            self.assertIn("missing artifact", check_evidence(root, require_artifacts=True)[0])
            manifest.write_text(json.dumps({"artifacts": []}))
            self.assertIn("missing artifact records", check_evidence(root)[0])

    def test_compatibility_tracks_project_enums_without_python_standard_library_drift(self):
        from scripts.checks.compatibility import _normalized_text, capture_module_contracts

        contracts = capture_module_contracts()
        state = contracts["dv_platform.physical"]["ClosureState"]
        self.assertEqual(state["signature"], "(value)")
        self.assertEqual(state["members"], {"PASSED": "passed", "FAILED": "failed", "UNKNOWN": "unknown"})
        self.assertNotIn("StrEnum", contracts["dv_platform.physical"])
        self.assertEqual(
            _normalized_text("(choose from 'init', 'status')"), _normalized_text("(choose from init, status)")
        )

    def test_compatibility_fingerprints_detect_api_and_driver_changes(self):
        manifest = {
            "format": "v1",
            "modules": {},
            "dataclasses": {},
            "cli": {},
            "entry_points": {},
            "schemas": {},
            "artifacts": [],
        }
        before = fingerprints(manifest)
        self.assertEqual(compare(before, fingerprints(manifest)), ())
        manifest["artifacts"] = [{"sha256": "changed"}]
        self.assertEqual(compare(before, fingerprints(manifest)), ("artifacts compatibility fingerprint changed",))
