import json
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from scripts.check_performance_qualification import compare_results, validate_result


def _result() -> dict[str, object]:
    return {
        "schema_version": 2,
        "profile": "enterprise-large-v1",
        "platform": "ubuntu-24.04",
        "platform_identity": {"system": "Linux", "release": "test"},
        "commit": "a" * 40,
        "worktree_clean": True,
        "wheel": {"path": "dv_platform.whl", "sha256": "b" * 64},
        "inputs": {"rtl_lines": 2_000_000, "xml_bytes": 134_217_728, "pdf_bytes": 67_108_864},
        "input_fingerprints": {
            "rtl": {"path": "scale.sv", "sha256": "c" * 64, "bytes": 1},
            "xml": {"path": "scale.xml", "sha256": "d" * 64, "bytes": 134_217_728},
            "pdf": {"path": "scale.pdf", "sha256": "e" * 64, "bytes": 67_108_864},
        },
        "tool_versions": {"python": "3.12.3", "defusedxml": "0.7.1", "pypdf": "6.12.0", "verilator": "5.020"},
        "stages": {
            "analyze": {"runtime_seconds": 100.0, "peak_rss_mb": 1000.0},
            "plan": {"runtime_seconds": 20.0, "peak_rss_mb": 500.0},
        },
        "reproducibility": {"hash_algorithm": "sha256", "python_hash_seed": "0", "command": "benchmark"},
    }


class PerformanceQualificationTests(TestCase):
    def test_checked_in_ubuntu_and_wsl_scale_evidence_passes(self) -> None:
        root = Path(__file__).resolve().parents[1] / "qualification"
        for platform in ("ubuntu24", "wsl2"):
            baseline = json.loads((root / f"{platform}-scale-baseline-v2.json").read_text(encoding="utf-8"))
            current = json.loads((root / f"{platform}-scale-current-v2.json").read_text(encoding="utf-8"))
            with self.subTest(platform=platform):
                self.assertEqual(validate_result(baseline, require_ga_scale=True), [])
                self.assertEqual(validate_result(current, require_ga_scale=True), [])
                self.assertEqual(compare_results(baseline, current), [])

    def test_ga_scale_result_and_ten_percent_boundary_pass(self) -> None:
        baseline = _result()
        current = deepcopy(baseline)
        current["stages"]["analyze"]["runtime_seconds"] = 110.0
        self.assertEqual(validate_result(current, require_ga_scale=True), [])
        self.assertEqual(compare_results(baseline, current), [])

    def test_regression_and_incomparable_inputs_fail_closed(self) -> None:
        baseline = _result()
        current = deepcopy(baseline)
        current["stages"]["analyze"]["peak_rss_mb"] = 1100.01
        self.assertTrue(any("regressed" in error for error in compare_results(baseline, current)))
        current = deepcopy(baseline)
        current["inputs"]["rtl_lines"] = 1
        self.assertEqual(compare_results(baseline, current), ["baseline and current input scales differ"])
        current = deepcopy(baseline)
        current["input_fingerprints"]["rtl"]["sha256"] = "f" * 64
        self.assertEqual(compare_results(baseline, current), ["baseline and current input_fingerprints differ"])

    def test_small_or_malformed_ga_result_is_rejected(self) -> None:
        result = _result()
        result["inputs"]["pdf_bytes"] = 1
        result["stages"]["plan"]["peak_rss_mb"] = 0
        errors = validate_result(result, require_ga_scale=True)
        self.assertTrue(any("below GA scale" in error for error in errors))
        self.assertTrue(any("invalid peak_rss_mb" in error for error in errors))
