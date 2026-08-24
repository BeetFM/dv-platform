"""Offline verification for closed signed deployment documents."""

from __future__ import annotations

import base64
import json
import subprocess
from hashlib import sha256
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any


def canonical_signed_document(document: dict[str, Any]) -> bytes:
    return json.dumps(
        {key: value for key, value in document.items() if key != "signature"},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=True,
    ).encode("ascii")


def verify_signed_document(document: dict[str, Any], document_path: Path, trust_root: Path) -> bool:
    signature = document.get("signature")
    if not isinstance(signature, dict) or set(signature) != {
        "certificate_file",
        "certificate_sha256",
        "value",
    }:
        return False
    executable = which("openssl")
    if executable is None:
        return False
    certificate = _contained(document_path.parent, signature["certificate_file"])
    if certificate is None or sha256(certificate.read_bytes()).hexdigest() != signature["certificate_sha256"]:
        return False
    if _run(executable, "verify", "-purpose", "any", "-CAfile", str(trust_root), str(certificate)).returncode:
        return False
    details = _run(executable, "x509", "-in", str(certificate), "-noout", "-text")
    if (
        details.returncode
        or "id-ecPublicKey" not in details.stdout
        or ("prime256v1" not in details.stdout and "P-256" not in details.stdout)
    ):
        return False
    try:
        raw_signature = base64.b64decode(signature["value"], validate=True)
    except (TypeError, ValueError):
        return False
    with TemporaryDirectory() as directory:
        public_key = Path(directory) / "public.pem"
        payload = Path(directory) / "payload.json"
        detached = Path(directory) / "signature.der"
        extracted = _run(executable, "x509", "-in", str(certificate), "-pubkey", "-noout")
        if extracted.returncode:
            return False
        public_key.write_text(extracted.stdout, encoding="utf-8")
        payload.write_bytes(canonical_signed_document(document))
        detached.write_bytes(raw_signature)
        return (
            _run(
                executable,
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                "-signature",
                str(detached),
                str(payload),
            ).returncode
            == 0
        )


def _contained(root: Path, value: object) -> Path | None:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        return None
    candidate = (root / value).resolve()
    return candidate if candidate.is_relative_to(root.resolve()) and candidate.is_file() else None


def _run(executable: str, *arguments: str) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            (executable, *arguments),
            capture_output=True,
            text=True,
            check=False,
            timeout=30,
        )
    except (OSError, subprocess.TimeoutExpired):
        return subprocess.CompletedProcess((executable, *arguments), 1, "", "")
