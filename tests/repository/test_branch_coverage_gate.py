import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from scripts.check_branch_coverage import evaluate_coverage, main


def _coverage(*, total=90.0, branches=10, covered=8):
    summary = {"percent_covered": total, "num_branches": branches, "covered_branches": covered}
    return {
        "meta": {"branch_coverage": True},
        "totals": summary,
        "files": {"src/module.py": {"summary": summary}},
    }


def _policy(*, total=80.0, branch=70.0):
    return {
        "schema_version": 1,
        "global": {"total": total, "branch": branch},
        "defaults": {"branch": branch},
        "files": {"src/module.py": {"total": total, "branch": branch}},
    }


class BranchCoverageGateTests(unittest.TestCase):
    def test_passing_policy_and_zero_branch_file(self) -> None:
        coverage = _coverage()
        coverage["files"]["src/no_branches.py"] = {
            "summary": {"percent_covered": 100, "num_branches": 0, "covered_branches": 0}
        }

        self.assertEqual(evaluate_coverage(coverage, _policy()), ())

    def test_global_default_explicit_and_missing_failures_are_reported(self) -> None:
        policy = _policy(total=95, branch=90)
        policy["files"]["src/missing.py"] = {"branch": 80}

        failures = evaluate_coverage(_coverage(total=89, branches=10, covered=7), policy)

        self.assertTrue(any(item.startswith("TOTAL: total") for item in failures))
        self.assertTrue(any("src/module.py: branch" in item for item in failures))
        self.assertIn("src/missing.py: required coverage record is missing", failures)

    def test_invalid_document_matrix(self) -> None:
        invalid = (
            ([], _policy()),
            (_coverage(), []),
            (_coverage(), {**_policy(), "schema_version": 2}),
            ({**_coverage(), "meta": {"branch_coverage": False}}, _policy()),
            ({**_coverage(), "totals": []}, _policy()),
            (_coverage(), {**_policy(), "defaults": []}),
            (_coverage(total=True), _policy()),
            (_coverage(branches=-1), _policy()),
            (_coverage(branches=1, covered=2), _policy()),
            (_coverage(), _policy(total=101)),
        )
        for coverage, policy in invalid:
            with self.subTest(coverage=coverage, policy=policy), self.assertRaises(ValueError):
                evaluate_coverage(coverage, policy)

    def test_cli_exit_codes_for_pass_failure_and_invalid_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            coverage_path = root / "coverage.json"
            policy_path = root / "policy.json"
            coverage_path.write_text(json.dumps(_coverage()), encoding="utf-8")
            policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
            self.assertEqual(main([str(coverage_path), "--policy", str(policy_path)]), 0)

            policy_path.write_text(json.dumps(_policy(total=99)), encoding="utf-8")
            self.assertEqual(main([str(coverage_path), "--policy", str(policy_path)]), 1)

            coverage_path.write_text("not-json", encoding="utf-8")
            self.assertEqual(main([str(coverage_path), "--policy", str(policy_path)]), 2)


if __name__ == "__main__":
    unittest.main()
