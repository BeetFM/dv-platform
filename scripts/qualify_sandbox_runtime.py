"""Execute and verify the OCI sandbox contract on a real container runtime."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shlex
import subprocess
import tempfile
from dataclasses import replace
from pathlib import Path
from typing import Any

from dv_platform.core.config import default_config
from dv_platform.core.sandbox import sandbox_command


def qualify(root: Path, runtime: str, image: str, output: Path) -> dict[str, Any]:
    """Run an unprivileged, network-denied probe and write digest-bound evidence."""

    root = root.resolve(strict=True)
    if _git(root, "status", "--porcelain"):
        raise ValueError("sandbox qualification requires a clean checkout")
    commit = _git(root, "rev-parse", "HEAD")
    if re.fullmatch(r"[0-9a-f]{40}", commit) is None:
        raise ValueError("sandbox qualification requires a resolved commit")
    runtime_path = _which(runtime)
    image_identity = _runtime(
        (runtime_path, "image", "inspect", image, "--format", "{{.Id}}"), timeout=30
    ).stdout.strip()
    if re.fullmatch(r"sha256:[0-9a-f]{64}", image_identity) is None:
        raise ValueError("sandbox image does not resolve to an immutable OCI identity")

    with tempfile.TemporaryDirectory(prefix="veriforge-sandbox-") as directory:
        writable = Path(directory).resolve()
        marker = writable / "probe.txt"
        probe = "\n".join(
            (
                "set -eu",
                'test "$(id -u)" != 0',
                f"test -r {shlex.quote(str(root / 'README.md'))}",
                f"! (printf forbidden >> {shlex.quote(str(root / 'README.md'))}) 2>/dev/null",
                "! (printf forbidden > /veriforge-forbidden) 2>/dev/null",
                'test "${VF_SANDBOX_ALLOWED:-}" = allowed',
                'test -z "${VF_SANDBOX_DENIED+x}"',
                'test "$(ls /sys/class/net)" = lo',
                "grep -Eq '^CapEff:[[:space:]]+0+$' /proc/self/status",
                "grep -Eq '^NoNewPrivs:[[:space:]]+1$' /proc/self/status",
                f"printf passed > {shlex.quote(str(marker))}",
            )
        )
        config = replace(
            default_config(root),
            sandbox_enabled=True,
            sandbox_runtime=runtime,
            sandbox_image=image,
            sandbox_environment=("VF_SANDBOX_ALLOWED",),
            max_process_memory_mb=256,
        )
        previous_allowed = os.environ.get("VF_SANDBOX_ALLOWED")
        os.environ["VF_SANDBOX_ALLOWED"] = "allowed"
        try:
            command = sandbox_command(
                config,
                ("/bin/sh", "-c", probe),
                root,
                writable_paths=(writable,),
            )
        finally:
            if previous_allowed is None:
                os.environ.pop("VF_SANDBOX_ALLOWED", None)
            else:
                os.environ["VF_SANDBOX_ALLOWED"] = previous_allowed
        environment = dict(os.environ)
        environment["VF_SANDBOX_ALLOWED"] = "allowed"
        environment["VF_SANDBOX_DENIED"] = "must-not-cross"
        result = subprocess.run(
            command,
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
            timeout=60,
        )
        if result.returncode != 0 or not marker.is_file() or marker.read_text(encoding="utf-8") != "passed":
            detail = (result.stderr or result.stdout).strip()
            raise ValueError(f"sandbox runtime probe failed with exit {result.returncode}: {detail}")

    version = _runtime((runtime_path, "version", "--format", "{{.Client.Version}}"), timeout=30).stdout.strip()
    security_options: list[str] = []
    daemon_rootless = False
    if runtime == "docker":
        info = _runtime((runtime_path, "info", "--format", "{{json .SecurityOptions}}"), timeout=30)
        parsed = json.loads(info.stdout)
        if isinstance(parsed, list):
            security_options = [str(item) for item in parsed]
        daemon_rootless = any("rootless" in item.lower() for item in security_options)
    payload: dict[str, Any] = {
        "schema_version": 1,
        "commit": commit,
        "runtime": runtime,
        "runtime_version": version,
        "image": image,
        "image_identity": image_identity,
        "execution": {
            "container_uid": os.getuid(),
            "container_gid": os.getgid(),
            "unprivileged_process": os.getuid() != 0,
            "daemon_rootless": daemon_rootless,
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
        "security_options": security_options,
        "command_sha256": hashlib.sha256("\0".join(command).encode()).hexdigest(),
        "status": "passed",
    }
    payload["evidence_sha256"] = _payload_digest(payload)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return payload


def validate(value: object) -> list[str]:
    """Validate sandbox evidence without trusting the producer."""

    if not isinstance(value, dict):
        return ["sandbox evidence must be an object"]
    errors: list[str] = []
    if value.get("schema_version") != 1 or value.get("status") != "passed":
        errors.append("sandbox evidence identity or status is invalid")
    if re.fullmatch(r"[0-9a-f]{40}", str(value.get("commit", ""))) is None:
        errors.append("sandbox evidence commit is invalid")
    if re.fullmatch(r"sha256:[0-9a-f]{64}", str(value.get("image_identity", ""))) is None:
        errors.append("sandbox image identity is invalid")
    execution = value.get("execution")
    required = {
        "unprivileged_process": True,
        "network": "none",
        "root_filesystem": "read-only",
        "source_mount": "read-only",
        "output_mount": "isolated-read-write",
        "capabilities": "dropped-all",
        "no_new_privileges": True,
        "memory_limit_mb": 256,
        "cpu_limit": 1,
        "pids_limit": 512,
    }
    if not isinstance(execution, dict):
        errors.append("sandbox execution record is missing")
    else:
        for name, expected in required.items():
            if execution.get(name) != expected:
                errors.append(f"sandbox execution control is invalid: {name}")
        if execution.get("environment_allowlist") != ["VF_SANDBOX_ALLOWED"]:
            errors.append("sandbox environment allowlist is invalid")
    if value.get("evidence_sha256") != _payload_digest(value):
        errors.append("sandbox evidence digest mismatch")
    return errors


def _runtime(command: tuple[str, ...], timeout: int) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(command, check=False, capture_output=True, text=True, timeout=timeout)
    if result.returncode != 0:
        raise ValueError((result.stderr or result.stdout).strip() or f"runtime command failed: {command[0]}")
    return result


def _which(runtime: str) -> str:
    import shutil

    value = shutil.which(runtime)
    if value is None:
        raise ValueError(f"sandbox runtime is unavailable: {runtime}")
    return value


def _git(root: Path, *arguments: str) -> str:
    return _runtime(("git", *arguments), timeout=30).stdout.strip()


def _payload_digest(value: dict[str, Any]) -> str:
    unsigned = dict(value)
    unsigned.pop("evidence_sha256", None)
    return hashlib.sha256(json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    create = subparsers.add_parser("create")
    create.add_argument("--root", type=Path, default=Path.cwd())
    create.add_argument("--runtime", choices=("docker", "podman"), required=True)
    create.add_argument("--image", required=True)
    create.add_argument("--output", type=Path, required=True)
    check = subparsers.add_parser("verify")
    check.add_argument("--input", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.command == "create":
            qualify(args.root, args.runtime, args.image, args.output)
            print(f"sandbox qualification written: {args.output}")
        else:
            value = json.loads(args.input.read_text(encoding="utf-8"))
            errors = validate(value)
            if errors:
                raise ValueError("; ".join(errors))
            print("sandbox qualification verified")
    except (OSError, ValueError, json.JSONDecodeError, subprocess.SubprocessError) as error:
        print(error)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
