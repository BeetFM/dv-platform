import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.enterprise.evidence import verify_pilot_evidence


class PilotEvidenceTests(unittest.TestCase):
    def test_pilot_evidence_requires_exact_rc_closure_and_signature(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "pilot.sigstore.json"
            bundle.write_text("{}", encoding="utf-8")
            payload = {
                "schema_version": 1,
                "pilot_id": "pilot-1",
            "rc_version": "1.0.0rc2",
                "wheel_sha256": "a" * 64,
                "commit": "b" * 40,
                "profile": "systemverilog-heavy",
                "accepted": True,
                "executed_at": "2026-07-22T12:00:00Z",
                "checks": {"total": 12, "passed": 12, "failed": 0, "skipped": 0},
                "artifact_sha256": "c" * 64,
                "upgrade": "passed",
                "rollback": "passed",
                "approver": "enterprise-owner",
                "signer": {"identity": "pilot@example.com", "issuer": "https://issuer.example"},
                "signature": {"kind": "sigstore", "bundle": bundle.name},
            }
            path = root / "pilot.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            calls = []
            result = verify_pilot_evidence(path, lambda source, signature, _value: calls.append((source, signature)))
            self.assertTrue(result["accepted"])
            self.assertEqual(calls, [(path, bundle)])

            payload["checks"]["skipped"] = 1
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "closure"):
                verify_pilot_evidence(path, lambda *_args: None)

            invalid_cases = (
                ("pilot_id", "bad identity!", "identity"),
                ("wheel_sha256", "short", "wheel_sha256"),
                ("profile", "unsupported", "accepted required profile"),
                ("executed_at", "not-a-time", "executed_at"),
                ("approver", "", "approval"),
                ("signer", {}, "signer identity"),
                ("signature", {"kind": "sigstore", "bundle": "../escape"}, "unsafe"),
            )
            payload["checks"]["skipped"] = 0
            for field, value, message in invalid_cases:
                candidate = dict(payload)
                candidate[field] = value
                path.write_text(json.dumps(candidate), encoding="utf-8")
                with self.subTest(field=field), self.assertRaisesRegex(ValueError, message):
                    verify_pilot_evidence(path, lambda *_args: None)


if __name__ == "__main__":
    unittest.main()
