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

    def test_runtime_editor_cache_and_eda_artifacts_are_ignored(self) -> None:
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
            "build/sim_build/result.xml",
            "build/obj_dir/Vtop",
            "waves/design.vcd",
            "waves/design.fst",
            "sim/result.wlf",
            "sim/result.wdb",
            "sim/design.vvp",
        )
        for relative in ignored:
            with self.subTest(relative=relative):
                self.assertTrue(self._is_ignored(relative))

    def test_source_json_and_xml_remain_visible(self) -> None:
        visible = (
            "schemas/rtl/dvsem-v2.schema.json",
            "qualification/policies/ga-gates-v1.json",
            "tests/fixtures/mutations/protocol/ahb_lite_registers.json",
            "tests/fixtures/verilator/simple_counter/Vsimple_counter.xml",
        )
        for relative in visible:
            with self.subTest(relative=relative):
                self.assertFalse(self._is_ignored(relative))


if __name__ == "__main__":
    unittest.main()
