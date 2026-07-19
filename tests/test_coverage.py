import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.coverage import import_coverage_reports, read_coverage_summary
from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.core.config import default_config
from dv_platform.core.models import CoveragePolicy


class CoverageImportTests(unittest.TestCase):
    def test_import_lcov_merges_counts_and_enforces_thresholds(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(
                default_config(repo),
                coverage_policy=CoveragePolicy(line_minimum=80.0, branch_minimum=60.0),
            )
            first = repo / "first.info"
            first.write_text(
                "SF:rtl/a.sv\nLF:10\nLH:9\nBRF:4\nBRH:3\nend_of_record\n",
                encoding="utf-8",
            )
            second = repo / "second.info"
            second.write_text(
                "SF:rtl/b.sv\nLF:10\nLH:7\nBRF:6\nBRH:3\nend_of_record\n",
                encoding="utf-8",
            )

            path, summary = import_coverage_reports(config, (first, second))

            self.assertEqual(path, repo / ".dv-platform" / "coverage" / "summary.json")
            self.assertEqual(summary["metrics"]["line"]["percentage"], 80.0)
            self.assertEqual(summary["metrics"]["branch"]["percentage"], 60.0)
            self.assertTrue(summary["passed"])
            self.assertEqual(read_coverage_summary(config), summary)
            self.assertTrue(any(gap["module"] == "rtl/b.sv" for gap in summary["gaps"]))

    def test_import_json_reports_missing_configured_metric_as_failed(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(
                default_config(repo),
                coverage_policy=CoveragePolicy(toggle_minimum=70.0),
            )
            report = repo / "coverage.json"
            report.write_text(json.dumps({"metrics": {"line": 95.0}}), encoding="utf-8")

            _path, summary = import_coverage_reports(config, (report,))

            self.assertFalse(summary["passed"])
            self.assertEqual(summary["gates"][0]["reason"], "metric missing")

    def test_status_policy_requires_import_when_coverage_policy_is_enabled(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = replace(
                default_config(Path(temp_dir)),
                coverage_policy=CoveragePolicy(functional_minimum=75.0),
            )

            failures = evaluate_status_policy(collect_platform_status(config), require_tools=False)

            self.assertIn("coverage_missing", {failure["code"] for failure in failures})


if __name__ == "__main__":
    unittest.main()
