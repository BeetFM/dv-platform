import json
import subprocess
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.qualification.ga_evidence import generate, verify, verify_context


class GAEvidenceTests(unittest.TestCase):
    def test_clean_commit_evidence_binds_tests_coverage_workflow_and_artifacts(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: test\n", encoding="utf-8")
            (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            log = root / "test.log"
            log.write_text("Ran 12 tests in 1.0s\n\nOK (skipped=2)\n", encoding="utf-8")
            coverage = root / "coverage.json"
            coverage.write_text(
                json.dumps({"totals": {"percent_covered": 90.5, "num_branches": 20, "covered_branches": 18}}),
                encoding="utf-8",
            )
            artifacts = root / "artifacts"
            artifacts.mkdir()
            (artifacts / "wheel.whl").write_bytes(b"wheel")
            output = root / "evidence.json"
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "fixture"), cwd=root, check=True)

            result = generate(9, root, log, coverage, artifacts, output)
            self.assertEqual(result["tests"], {"passed": 10, "skipped": 2, "failed": 0})
            self.assertEqual(result["coverage"]["branch"], 90.0)
            self.assertEqual(verify(output)["evidence_sha256"], result["evidence_sha256"])
            payload = json.loads(output.read_text(encoding="utf-8"))
            payload["tests"]["failed"] = 1
            output.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify(output)

    def test_dirty_checkout_is_rejected(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            (root / "untracked").write_text("dirty", encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "clean checkout"):
                generate(9, root, root / "missing", root / "missing", root, root / "out")

    def test_context_rejects_artifact_substitution_and_accepts_exact_candidate(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".github" / "workflows").mkdir(parents=True)
            (root / ".github" / "workflows" / "ci.yml").write_text("name: test\n", encoding="utf-8")
            (root / "uv.lock").write_text("version = 1\n", encoding="utf-8")
            artifacts = root.parent / f"artifacts-{root.name}"
            artifacts.mkdir()
            (artifacts / "wheel.whl").write_bytes(b"wheel")
            log = root / "test.log"
            log.write_text("Ran 2 tests in 1.0s\n\nOK\n", encoding="utf-8")
            coverage = root / "coverage.json"
            coverage.write_text(json.dumps({"totals": {"percent_covered": 90, "num_branches": 1, "covered_branches": 1}}), encoding="utf-8")
            subprocess.run(("git", "init", "-q"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.email", "test@example.com"), cwd=root, check=True)
            subprocess.run(("git", "config", "user.name", "Test"), cwd=root, check=True)
            subprocess.run(("git", "add", "."), cwd=root, check=True)
            subprocess.run(("git", "commit", "-qm", "fixture"), cwd=root, check=True)
            evidence = root / "evidence.json"
            generate(9, root, log, coverage, artifacts, evidence)
            verify_context(evidence, root=root, artifacts=artifacts, expected_stage=9)
            (artifacts / "wheel.whl").write_bytes(b"substituted")
            with self.assertRaisesRegex(ValueError, "artifact subjects differ"):
                verify_context(evidence, root=root, artifacts=artifacts, expected_stage=9)


if __name__ == "__main__":
    unittest.main()
