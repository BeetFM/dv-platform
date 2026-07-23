#!/usr/bin/env python3
"""Standalone runner shipped in a dv-platform vendor qualification bundle."""

import argparse
import hashlib
import json
import os
import pathlib
import subprocess
from datetime import UTC, datetime


def canonical(payload):
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


def digest(payload):
    return hashlib.sha256(canonical(payload).encode("utf-8")).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--request", type=pathlib.Path, default=pathlib.Path("qualification-request.json"))
    parser.add_argument("--tool-name", required=True)
    parser.add_argument("--tool-version", required=True)
    parser.add_argument("--timeout-seconds", type=float, default=3600.0)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not command or not 0 < args.timeout_seconds <= 86400:
        parser.error("a command and timeout within 1..86400 seconds are required")
    root = args.request.resolve().parent
    request = json.loads(args.request.read_text(encoding="utf-8"))
    for name, expected in request["fixtures"].items():
        fixture = root / "fixtures" / name
        observed = hashlib.sha256(fixture.read_bytes()).hexdigest()
        if observed != expected:
            raise SystemExit("qualification fixture hash mismatch: " + name)
    result_path = root / "enterprise-result.json"
    environment = dict(os.environ)
    environment["DV_PLATFORM_RESULT_PATH"] = str(result_path)
    environment["DV_PLATFORM_QUALIFICATION_ROOT"] = str(root)
    completed = subprocess.run(
        command,
        cwd=root,
        env=environment,
        stdin=subprocess.DEVNULL,
        timeout=args.timeout_seconds,
        check=False,
    )
    result = json.loads(result_path.read_text(encoding="utf-8"))
    observed_checks = {item.get("check_id") for item in result.get("checks", []) if item.get("status") == "passed"}
    required_checks = set(request["required_check_ids"])
    if result.get("schema_version") != 1 or result.get("status") != "passed" or not required_checks <= observed_checks:
        raise SystemExit("normalized vendor result does not pass the qualification request")
    executed_at = datetime.now(UTC).isoformat().replace("+00:00", "Z")
    attestation = {
        "schema_version": 1,
        "request": request,
        "request_sha256": digest(request),
        "tool": {"name": args.tool_name, "version": args.tool_version},
        "executed_at": executed_at,
        "command": {"executable": pathlib.Path(command[0]).name, "return_code": completed.returncode},
        "result": result,
        "result_sha256": digest(result),
    }
    attestation["integrity_sha256"] = digest(attestation)
    (root / "qualification-attestation.json").write_text(
        json.dumps(attestation, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )
    return 0 if completed.returncode == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
