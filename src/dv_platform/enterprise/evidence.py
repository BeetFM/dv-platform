"""Structural and cryptographic verification of release and pilot evidence."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable
from datetime import datetime
from pathlib import Path
from typing import Any

SignatureVerifier = Callable[[Path, Path, dict[str, Any]], None]


def verify_pilot_evidence(path: Path, signature_verifier: SignatureVerifier | None = None) -> dict[str, Any]:
    """Verify content-free pilot acceptance and its detached signature."""

    source = path.resolve(strict=True)
    value = json.loads(source.read_text(encoding="utf-8"))
    _validate_pilot_record(value)
    bundle = _pilot_signature_bundle(source, value)
    (signature_verifier or _verify_signature)(source, bundle, value)
    return value


def _validate_pilot_record(value: object) -> None:
    if not isinstance(value, dict) or value.get("schema_version") != 1 or value.get("rc_version") != "1.0.0rc3":
        raise ValueError("unsupported pilot evidence schema or RC lineage")
    if re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}", str(value.get("pilot_id", ""))) is None:
        raise ValueError("pilot evidence identity is invalid")
    for field, width in (("wheel_sha256", 64), ("artifact_sha256", 64), ("commit", 40)):
        if re.fullmatch(rf"[0-9a-f]{{{width}}}", str(value.get(field, ""))) is None:
            raise ValueError(f"pilot evidence {field} is invalid")
    if value.get("profile") not in {"systemverilog-heavy", "vhdl-mixed-tool"} or value.get("accepted") is not True:
        raise ValueError("pilot evidence is not an accepted required profile")
    try:
        datetime.fromisoformat(str(value["executed_at"]).replace("Z", "+00:00"))
    except (KeyError, ValueError) as error:
        raise ValueError("pilot evidence executed_at is invalid") from error
    checks = value.get("checks")
    if (
        not isinstance(checks, dict)
        or not isinstance(checks.get("total"), int)
        or checks.get("total", 0) < 1
        or checks.get("passed") != checks.get("total")
        or checks.get("failed") != 0
        or checks.get("skipped") != 0
    ):
        raise ValueError("pilot evidence check closure is incomplete")
    if (
        value.get("upgrade") != "passed"
        or value.get("rollback") != "passed"
        or not str(value.get("approver", "")).strip()
    ):
        raise ValueError("pilot evidence upgrade, rollback, or approval is incomplete")


def _pilot_signature_bundle(source: Path, value: dict[str, Any]) -> Path:
    signer, signature = value.get("signer"), value.get("signature")
    if not isinstance(signer, dict) or not isinstance(signature, dict):
        raise ValueError("pilot evidence signer or signature is missing")
    if not str(signer.get("identity", "")).strip() or not str(signer.get("issuer", "")).strip():
        raise ValueError("pilot evidence signer identity is incomplete")
    relative = Path(str(signature.get("bundle", "")))
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("pilot evidence signature bundle path is unsafe")
    candidate = source.parent / relative
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError("pilot evidence signature bundle must be adjacent and regular")
    bundle = candidate.resolve(strict=True)
    if bundle.parent != source.parent:
        raise ValueError("pilot evidence signature bundle must be adjacent and regular")
    return bundle


def _verify_signature(source: Path, bundle: Path, value: dict[str, Any]) -> None:
    signature = value["signature"]
    signer = value["signer"]
    kind = signature.get("kind")
    command: tuple[str, ...]
    if kind == "sigstore":
        executable = shutil.which("cosign")
        if executable is None:
            raise ValueError("cosign is required to verify pilot evidence")
        command = (
            executable,
            "verify-blob",
            "--bundle",
            str(bundle),
            "--certificate-identity",
            str(signer["identity"]),
            "--certificate-oidc-issuer",
            str(signer["issuer"]),
            str(source),
        )
    elif kind == "pki":
        executable = shutil.which("openssl")
        trust_root = Path(str(signature.get("trust_root", ""))).expanduser().resolve(strict=True)
        if executable is None or not trust_root.is_file() or trust_root.is_symlink():
            raise ValueError("openssl and a regular pilot PKI trust root are required")
        command = (
            executable,
            "cms",
            "-verify",
            "-binary",
            "-inform",
            "DER",
            "-in",
            str(bundle),
            "-content",
            str(source),
            "-CAfile",
            str(trust_root),
            "-purpose",
            "any",
            "-out",
            os.devnull,
        )
    else:
        raise ValueError(f"unsupported pilot signature kind: {kind}")
    result = subprocess.run(command, check=False, capture_output=True, timeout=60)
    if result.returncode != 0:
        raise ValueError("pilot evidence signature verification failed")
