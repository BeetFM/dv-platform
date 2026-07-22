import json
from copy import deepcopy
from pathlib import Path
from unittest import TestCase

from scripts.qualify_sandbox_runtime import validate


class SandboxQualificationTests(TestCase):
    def test_checked_in_runtime_evidence_is_valid(self) -> None:
        path = Path(__file__).resolve().parents[1] / "qualification" / "oci-sandbox-runtime-v1.json"
        if not path.is_file():
            self.skipTest("runtime evidence is created from the next clean implementation commit")
        self.assertEqual(validate(json.loads(path.read_text(encoding="utf-8"))), [])

    def test_missing_control_and_digest_tampering_fail_closed(self) -> None:
        evidence = _evidence()
        evidence["evidence_sha256"] = _digest(evidence)
        self.assertEqual(validate(evidence), [])
        damaged = deepcopy(evidence)
        damaged["execution"]["network"] = "host"
        errors = validate(damaged)
        self.assertTrue(any("network" in error for error in errors))
        self.assertTrue(any("digest" in error for error in errors))


def _evidence() -> dict:
    return {
        "schema_version": 1,
        "commit": "a" * 40,
        "runtime": "docker",
        "runtime_version": "29.5.2",
        "image": "example@sha256:" + "b" * 64,
        "image_identity": "sha256:" + "b" * 64,
        "execution": {
            "container_uid": 1000,
            "container_gid": 1000,
            "unprivileged_process": True,
            "daemon_rootless": False,
            "network": "none",
            "root_filesystem": "read-only",
            "source_mount": "read-only",
            "output_mount": "isolated-read-write",
            "capabilities": "dropped-all",
            "no_new_privileges": True,
            "environment_allowlist": ["VF_SANDBOX_ALLOWED"],
            "memory_limit_mb": 256,
            "cpu_limit": 1,
            "pids_limit": 512,
        },
        "security_options": [],
        "command_sha256": "c" * 64,
        "status": "passed",
    }


def _digest(value: dict) -> str:
    import hashlib

    unsigned = dict(value)
    unsigned.pop("evidence_sha256", None)
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
