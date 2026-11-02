import subprocess
import unittest

from tests.support.paths import REPOSITORY_ROOT


class GitignorePolicyTests(unittest.TestCase):
    def _is_ignored(self, relative: str) -> bool:
        completed = subprocess.run(
            ("git", "check-ignore", "--no-index", "--quiet", relative),
            cwd=REPOSITORY_ROOT,
            check=False,
        )
        self.assertIn(completed.returncode, (0, 1))
        return completed.returncode == 0

    def test_runtime_editor_cache_and_native_artifacts_are_ignored(self) -> None:
        ignored = (
            "nested/.dv-platform/state.json",
            "run/events.jsonl",
            "run/results.sqlite3",
            "run/results.db-wal",
            "run/worker.pid",
            "run/output.log",
            ".idea/workspace.xml",
            ".vscode/settings.json",
            ".env.local",
            ".tox/state",
            "waves/design.vcd",
            "waves/design.fst",
            "sim/design.vvp",
            "run/pd-final.odb",
            "run/results/design.nom.spef",
            "run/design.sdf",
            "run/design.saif",
            "run/verification.lyrdb",
            "qualification/evidence/PHYS-01/local-run.json",
            "qualification/evidence/PHYS-01/artifacts/run/report.xml",
            "qualification/evidence/PROTO-01/local-run.json",
            "schemas/enterprise/physical-evidence-v1.schema.json",
            "qualification/policies/openroad-fixture-v1.json",
            "scripts/qualification/sky130.py",
        )
        for relative in ignored:
            with self.subTest(relative=relative):
                self.assertTrue(self._is_ignored(relative))

    def test_source_json_and_xml_remain_visible(self) -> None:
        visible = (
            "src/dv_platform/sky130-pin.json",
            "tests/fixtures/project.json",
            "tests/fixtures/timing-report.xml",
        )
        for relative in visible:
            with self.subTest(relative=relative):
                self.assertFalse(self._is_ignored(relative))


if __name__ == "__main__":
    unittest.main()
