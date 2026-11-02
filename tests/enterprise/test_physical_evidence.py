import importlib.util
import json
import unittest
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.core.config import default_config, validate_config
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
        "tool_versions": {"openroad": "fixture-1"},
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
        "tool": "openroad",
        "tool_version": "fixture-1",
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
    def test_runtime_allows_only_openroad_asic_evidence(self):
        for tool, domain in (
            ("vivado", "fpga_implementation"),
            ("spyglass", "asic_cdc_rdc"),
            ("primetime", "asic_timing"),
            ("primepower", "asic_power"),
            ("jaspergold", "asic_cdc_rdc"),
            ("tempus", "asic_timing"),
            ("voltus", "asic_power"),
            ("openroad", "fpga_implementation"),
            ("openroad", "asic_cdc_rdc"),
        ):
            report = {**_report(), "tool": tool, "domain": domain}
            with self.subTest(tool=tool, domain=domain), self.assertRaises(PhysicalEvidenceError):
                validate_physical_evidence(report, _policy(), verify_signature=lambda _value: True)

    def test_fpga_physical_configuration_is_rejected(self):
        config = replace(
            default_config(Path.cwd()),
            product=ProductConfig(required_physical_domains=("fpga_implementation",)),
        )
        self.assertTrue(any("required_physical_domains" in item.message for item in validate_config(config)))

    def test_openroad_adapter_normalizes_and_imports_signed_evidence(self):
        path = Path.cwd() / "enterprise/src/dv_platform_enterprise/physical.py"
        spec = importlib.util.spec_from_file_location("openroad_physical", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        adapter = module.OpenROADPhysicalEvidenceAdapter()
        report = _report()
        report["findings"][0]["path"] = ".\\top\\u_sram"
        normalized = adapter.normalize(report)
        self.assertEqual(normalized["findings"][0]["path"], "top/u_sram")
        self.assertEqual(report["findings"][0]["path"], ".\\top\\u_sram")
        for invalid in (
            {**report, "tool": "tempus"},
            {**report, "findings": []},
            {**report, "clocks_domains": [report["clocks_domains"][0], None]},
        ):
            with self.assertRaises(ValueError):
                adapter.normalize(invalid)

        from dv_platform.product import ResolvedProductPlan

        plan = ResolvedProductPlan(
            "enterprise", "fixture", "enterprise", frozenset({"physical.asic.timing"}), "valid", 1, False
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            report_path = root / "report.json"
            policy_path = root / "policy.json"
            report_path.write_text(json.dumps(normalized), encoding="utf-8")
            policy_path.write_text(json.dumps(_policy()), encoding="utf-8")
            config = replace(default_config(root), product=ProductConfig(required_physical_domains=("asic_timing",)))
            module.import_physical_evidence(
                config, report_path, policy_path, plan, verify_signature=lambda _value: True
            )
            self.assertEqual(collect_physical_status(config)["overall"], "passed")
            closure_path = config.work_dir / "physical/closure.json"
            accepted = closure_path.read_bytes()
            with self.assertRaisesRegex(PhysicalEvidenceError, "signature is untrusted"):
                module.import_physical_evidence(
                    config, report_path, policy_path, plan, verify_signature=lambda _value: False
                )
            self.assertEqual(closure_path.read_bytes(), accepted)

    def test_imported_domains_cannot_combine_results_from_different_design_inputs(self):
        from dv_platform.product import ResolvedProductPlan

        path = Path.cwd() / "enterprise/src/dv_platform_enterprise/physical.py"
        spec = importlib.util.spec_from_file_location("physical_import_identity", path)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        plan = ResolvedProductPlan(
            "enterprise",
            "fixture",
            "enterprise",
            frozenset({"physical.asic.timing", "physical.asic.power"}),
            "valid",
            1,
            False,
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root), product=ProductConfig(required_physical_domains=("asic_timing", "asic_power"))
            )
            report, policy = _report(), _policy()
            for domain in ("asic_timing", "asic_power"):
                report["domain"] = domain
                (root / "report.json").write_text(json.dumps(report))
                (root / "policy.json").write_text(json.dumps(policy))
                module.import_physical_evidence(
                    config, root / "report.json", root / "policy.json", plan, verify_signature=lambda _value: True
                )
            self.assertEqual(collect_physical_status(config)["overall"], "passed")
            report.update(domain="asic_timing", source_sha256="c" * 64)
            policy["source_sha256"] = report["source_sha256"]
            (root / "report.json").write_text(json.dumps(report))
            (root / "policy.json").write_text(json.dumps(policy))
            result = module.import_physical_evidence(
                config, root / "report.json", root / "policy.json", plan, verify_signature=lambda _value: True
            )
            self.assertEqual(collect_physical_status(config)["overall"], "unknown")
            payload = json.loads(result.read_text())
            self.assertEqual(payload["domains"], {"asic_timing": "passed"})
            deadline = datetime.fromisoformat(payload["valid_until"]["asic_timing"])
            self.assertEqual(deadline, datetime.fromisoformat(report["generated_at"]) + timedelta(hours=24))

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

    def test_malformed_evidence_and_policy_never_produce_passing_closure(self):
        cases = (
            {"complete": "false"},
            {"schema_version": True},
            {"clocks_domains": [None]},
            {"pdk_files": "sky130.lib"},
            {"corners": ["tt_025C_1v80", "tt_025C_1v80"]},
            {"generated_at": "2026-10-26T10:00:00"},
            {"source_sha256": "not-a-digest"},
        )
        for mutation in cases:
            with self.subTest(mutation=mutation), self.assertRaises(PhysicalEvidenceError):
                validate_physical_evidence({**_report(), **mutation}, _policy(), verify_signature=lambda _value: True)
        for mutation in ({"value": float("nan")}, {"waived": "false"}, {"hierarchy": []}, {"unit": []}):
            report = _report()
            report["findings"][0].update(mutation)
            with self.subTest(mutation=mutation), self.assertRaises(PhysicalEvidenceError):
                validate_physical_evidence(report, _policy(), verify_signature=lambda _value: True)
        for mutation in ({"max_age_hours": float("nan")}, {"tool_versions": []}, {"allowed_units": [None]}):
            with self.subTest(mutation=mutation), self.assertRaises(PhysicalEvidenceError):
                validate_physical_evidence(_report(), {**_policy(), **mutation}, verify_signature=lambda _value: True)

    def test_every_declared_corner_and_mode_requires_parsed_findings(self):
        report, policy = _report(), _policy()
        report["corners"].append("ss")
        policy["corners"].append("ss")
        with self.assertRaisesRegex(PhysicalEvidenceError, "every required corner"):
            validate_physical_evidence(report, policy, verify_signature=lambda _value: True)

    def test_cached_pass_becomes_unknown_after_evidence_or_waiver_expiry(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)), product=ProductConfig(required_physical_domains=("asic_timing",))
            )
            path = config.work_dir / "physical/closure.json"
            path.parent.mkdir(parents=True)
            for expiry in (None, "not-a-date", (datetime.now(UTC) - timedelta(seconds=1)).isoformat()):
                payload = {
                    "schema_version": 1,
                    "domains": {"asic_timing": "passed"},
                    "valid_until": {"asic_timing": expiry},
                }
                path.write_text(json.dumps(payload))
                self.assertEqual(collect_physical_status(config)["overall"], "unknown")

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

    def test_closure_status_validates_schema_and_domain_values_on_all_supported_pythons(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)), product=ProductConfig(required_physical_domains=("asic_timing",))
            )
            path = config.work_dir / "physical/closure.json"
            path.parent.mkdir(parents=True)
            for payload in (
                {
                    "schema_version": 1,
                    "domains": {"asic_timing": "passed"},
                    "valid_until": {"asic_timing": (datetime.now(UTC) + timedelta(hours=1)).isoformat()},
                },
                {"schema_version": 99, "domains": {"asic_timing": "passed"}},
                {"schema_version": 1, "domains": {"asic_timing": []}},
                {"schema_version": 1, "domains": {"fpga_implementation": "passed"}},
                [],
            ):
                with self.subTest(payload=payload):
                    path.write_text(json.dumps(payload))
                    valid = (
                        isinstance(payload, dict)
                        and payload.get("schema_version") == 1
                        and payload.get("domains") == {"asic_timing": "passed"}
                    )
                    self.assertEqual(collect_physical_status(config)["overall"], "passed" if valid else "unknown")

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
