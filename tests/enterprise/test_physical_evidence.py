import hashlib
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path

from dv_platform.core.config import default_config
from dv_platform.domain.models import ProductConfig
from dv_platform.physical import (
    ClosureState,
    PhysicalClosure,
    PhysicalEvidenceError,
    collect_physical_status,
    validate_physical_evidence,
)

_DIGEST = "a" * 64


def _policy():
    return {
        "schema_version": 1,
        "tool_versions": {"tempus": "23.10-p001"},
        "design": "sky130-openram-fixture",
        "source_sha256": _DIGEST,
        "netlist_sha256": _DIGEST,
        "constraints_sha256": _DIGEST,
        "pdk": "sky130A-pinned",
        "pdk_files": ["sky130_fd_sc_hd__tt_025C_1v80.lib"],
        "libraries": ["openram_sram_1rw1r_32x256"],
        "corners": ["tt_025C_1v80"],
        "modes": ["functional"],
        "max_age_hours": 24,
        "allowed_units": ["ns"],
    }


def _report():
    return {
        "schema_version": 1,
        "domain": "asic_timing",
        "tool": "tempus",
        "tool_version": "23.10-p001",
        "design": "sky130-openram-fixture",
        "source_sha256": _DIGEST,
        "netlist_sha256": _DIGEST,
        "constraints_sha256": _DIGEST,
        "pdk": "sky130A-pinned",
        "pdk_files": ["sky130_fd_sc_hd__tt_025C_1v80.lib"],
        "libraries": ["openram_sram_1rw1r_32x256"],
        "corners": ["tt_025C_1v80"],
        "modes": ["functional"],
        "clocks_domains": [{"clock": "clk", "domain": "core"}],
        "findings": [
            {
                "finding_id": "TIMING-SUMMARY",
                "severity": "info",
                "path": None,
                "hierarchy": "top",
                "clock_domain": "core",
                "corner": "tt_025C_1v80",
                "mode": "functional",
                "unit": "ns",
                "value": 0.2,
                "waived": False,
                "waiver_id": None,
            }
        ],
        "waivers": [],
        "units": ["ns"],
        "complete": True,
        "generated_at": datetime.now(UTC).isoformat(),
        "report_sha256": "b" * 64,
        "signature": {"kind": "fixture"},
    }


class PhysicalEvidenceTests(unittest.TestCase):
    def test_sky130_openram_fixture_assets_match_pinned_manifest(self):
        root = Path.cwd()
        manifest = json.loads((root / "qualification/policies/physical-fixture-v1.json").read_text(encoding="utf-8"))
        for asset in manifest["local_assets"]:
            self.assertEqual(hashlib.sha256((root / asset["path"]).read_bytes()).hexdigest(), asset["sha256"])

    def test_clean_complete_signed_report_passes(self):
        domain, state = validate_physical_evidence(
            _report(),
            _policy(),
            verify_signature=lambda _value: True,
        )
        self.assertEqual((domain, state), ("asic_timing", ClosureState.PASSED))

    def test_absence_stale_identity_and_partial_findings_fail_closed(self):
        mutations = []
        empty = _report()
        empty["findings"] = []
        mutations.append(empty)
        stale = _report()
        stale["generated_at"] = (datetime.now(UTC) - timedelta(days=2)).isoformat()
        mutations.append(stale)
        mismatch = _report()
        mismatch["netlist_sha256"] = "c" * 64
        mutations.append(mismatch)
        partial = _report()
        del partial["findings"][0]["corner"]
        mutations.append(partial)
        for report in mutations:
            with self.subTest(report=report):
                with self.assertRaises(PhysicalEvidenceError):
                    validate_physical_evidence(report, _policy(), verify_signature=lambda _value: True)

    def test_expired_or_unbound_waiver_fails(self):
        report = _report()
        report["findings"][0].update({"severity": "critical", "waived": True, "waiver_id": "W-1"})
        report["waivers"] = [
            {
                "waiver_id": "W-1",
                "finding_ids": ["OTHER"],
                "approved_by": "maintainer",
                "expires_at": (datetime.now(UTC) + timedelta(days=1)).isoformat(),
                "reason": "fixture",
            }
        ]
        with self.assertRaises(PhysicalEvidenceError):
            validate_physical_evidence(report, _policy(), verify_signature=lambda _value: True)

    def test_logical_pass_never_overrides_physical_failure_or_unknown(self):
        failed = PhysicalClosure(ClosureState.PASSED, (("asic_timing", ClosureState.FAILED),))
        unknown = PhysicalClosure(ClosureState.PASSED, (("asic_power", ClosureState.UNKNOWN),))
        self.assertEqual(failed.overall, ClosureState.FAILED)
        self.assertEqual(unknown.overall, ClosureState.UNKNOWN)

    def test_required_missing_physical_domain_is_unknown(self):
        config = replace(
            default_config(Path.cwd()),
            product=ProductConfig(required_physical_domains=("asic_timing",)),
        )
        status = collect_physical_status(config)
        self.assertEqual(status["overall"], "unknown")
        self.assertEqual(status["domains"]["asic_timing"], "unknown")


if __name__ == "__main__":
    unittest.main()
