import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.status import collect_platform_status, evaluate_status_policy
from dv_platform.core.config import default_config
from dv_platform.qualification import (
    capability_ledger_status,
    load_capability_ledger,
    render_capability_table,
    validate_capability_ledger,
)
from dv_platform.qualification.evidence import validate_evidence_record


def _evidence(*, execution_kind: str = "real") -> dict[str, object]:
    digest = "a" * 64
    return {
        "schema_version": 1,
        "source_sha256": digest,
        "configuration_sha256": digest,
        "profile_sha256": digest,
        "profile_id": "axi4-1.0",
        "profile_version": "1.0",
        "role": "subordinate",
        "target": "cocotb",
        "tool_versions": {"iverilog": "12.0"},
        "commands": ["uv run qualification"],
        "expected_checks": ["axi4.accept"],
        "mutant_outcomes": [{"mutant_id": "stuck-ready", "killed": True, "check_ids": ["axi4.accept"]}],
        "coverage": {"schema_version": 3, "measured_ids": ["axi4.accept"], "missing_ids": []},
        "non_vacuity": "passed",
        "strict_status": "passed",
        "execution_kind": execution_kind,
    }


class CapabilityGovernanceTests(unittest.TestCase):
    def test_doc00_table_is_deterministic_and_matches_current_document(self) -> None:
        ledger, _origin = load_capability_ledger(Path.cwd())
        rendered = render_capability_table(ledger)
        document = (Path.cwd() / "docs" / "verification.md").read_text(encoding="utf-8")
        start = document.index("<!-- generated: capability-ledger-v1 -->")
        end = document.index("<!-- /generated: capability-ledger-v1 -->", start)
        embedded = document[start:].splitlines()[1 : document[start:end].count("\n")]
        self.assertEqual("\n".join(embedded) + "\n", rendered)
        self.assertEqual(render_capability_table(ledger), rendered)

    def test_packaged_ledger_is_closed_and_has_inverse_roles(self) -> None:
        ledger, _origin = load_capability_ledger(Path.cwd())
        self.assertEqual(validate_capability_ledger(ledger, repo_root=Path.cwd()), ())
        identities = {(cell["profile_id"], cell["role"], cell["target"]) for cell in ledger["cells"]}
        self.assertIn(("axi4-1.0", "manager", "formal"), identities)
        self.assertIn(("avalon-st-1.0", "source", "uvm"), identities)

    def test_runtime_eligibility_cannot_exceed_unsupported_ledger(self) -> None:
        ledger, _origin = load_capability_ledger(Path.cwd())
        runtime = (
            {
                "profile_id": "axi4-1.0",
                "profile_version": "1.0",
                "role": "manager",
                "target": "cocotb",
                "bound": {"maximum_burst_length": 256, "maximum_outstanding": 16, "timeout_cycles": 32},
                "executable": True,
            },
        )
        errors = validate_capability_ledger(ledger, repo_root=Path.cwd(), runtime_cells=runtime)
        self.assertTrue(any("exceeds ledger" in error for error in errors))

    def test_generated_hdl_language_targets_must_remain_at_parity(self) -> None:
        ledger, _origin = load_capability_ledger(Path.cwd())
        systemverilog = next(
            item
            for item in ledger["cells"]
            if item["profile_id"] == "axi4-1.0" and item["role"] == "subordinate" and item["target"] == "systemverilog"
        )
        systemverilog["state"] = "partial"
        systemverilog["evidence_digest"] = None
        systemverilog["evidence_path"] = None
        systemverilog["last_passing_source"] = None

        errors = validate_capability_ledger(ledger, repo_root=Path.cwd())

        self.assertTrue(any("SystemVerilog/Verilog/VHDL capability parity" in error for error in errors))

    def test_mocked_or_stale_evidence_cannot_support_cell(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "qualification" / "evidence").mkdir(parents=True)
            ledger, _origin = load_capability_ledger(Path.cwd())
            cell = next(
                item
                for item in ledger["cells"]
                if item["profile_id"] == "axi4-1.0" and item["role"] == "subordinate" and item["target"] == "cocotb"
            )
            record = _evidence(execution_kind="mocked")
            evidence_path = root / "qualification" / "evidence" / "record.json"
            raw = json.dumps(record, sort_keys=True).encode("utf-8")
            evidence_path.write_bytes(raw)
            cell["state"] = "supported"
            cell["evidence_path"] = "qualification/evidence/record.json"
            cell["evidence_digest"] = hashlib.sha256(raw).hexdigest()
            cell["last_passing_source"] = "b" * 40

            errors = validate_capability_ledger(ledger, repo_root=root)

            self.assertTrue(any("mocked evidence" in error for error in errors))
            self.assertEqual(validate_evidence_record(record), ())

    def test_status_reports_corrupt_source_ledger(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "qualification" / "policies"
            path.mkdir(parents=True)
            (path / "capability-ledger-v1.json").write_text("{", encoding="utf-8")
            status = capability_ledger_status(root)
            self.assertEqual(status["status"], "invalid")
            platform_status = collect_platform_status(default_config(root))
            failures = evaluate_status_policy(platform_status, require_tools=False)
            self.assertIn("capability_ledger_invalid", {failure["code"] for failure in failures})

    def test_project_without_local_ledger_resolves_authority_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            status = capability_ledger_status(Path(directory))

        self.assertEqual(status["status"], "valid", status["errors"])


if __name__ == "__main__":
    unittest.main()
