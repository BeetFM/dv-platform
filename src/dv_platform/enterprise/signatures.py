"""Independent detached signatures for proprietary qualification evidence."""

from __future__ import annotations

import json
import re
import subprocess
from dataclasses import dataclass
from datetime import datetime
from hashlib import sha256
from hmac import compare_digest
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any

SIGNATURE_MANIFEST_SCHEMA_VERSION = 1
SIGNATURE_TRUST_POLICY_SCHEMA_VERSION = 1
SIGNATURE_PURPOSE = "veriforge-vendor-qualification"
MAX_SIGNATURE_METADATA_BYTES = 1024 * 1024
MAX_SIGNATURE_ASSET_BYTES = 4 * 1024 * 1024
MAX_SIGNED_ATTESTATION_BYTES = 32 * 1024 * 1024
OPENSSL_TIMEOUT_SECONDS = 30.0
_SHA256 = re.compile(r"^[0-9a-f]{64}$")


class SignatureVerificationError(ValueError):
    """Raised when a qualification signature is malformed or untrusted."""


@dataclass(frozen=True)
class VerifiedQualificationSignature:
    kind: str
    identity: str
    issuer: str
    certificate_sha256: str
    manifest_sha256: str
    signed_at: str

    def as_payload(self) -> dict[str, str]:
        return {
            "kind": self.kind,
            "identity": self.identity,
            "issuer": self.issuer,
            "certificate_sha256": self.certificate_sha256,
            "manifest_sha256": self.manifest_sha256,
            "signed_at": self.signed_at,
        }


def verify_qualification_signature(
    attestation_path: Path,
    manifest_path: Path,
    trust_policy_path: Path,
) -> VerifiedQualificationSignature:
    """Verify an exact attestation against an independently administered PKI."""

    attestation = _attestation_bytes(attestation_path)
    manifest_raw, manifest = _read_document(manifest_path, "signature manifest")
    _, policy = _read_document(trust_policy_path, "signature trust policy")
    _exact_fields(
        manifest,
        {
            "schema_version",
            "purpose",
            "signature_kind",
            "attestation_sha256",
            "signature_file",
            "certificate_file",
            "signed_at",
        },
        "signature manifest",
    )
    if manifest.get("schema_version") != SIGNATURE_MANIFEST_SCHEMA_VERSION:
        raise SignatureVerificationError("unsupported signature manifest schema_version")
    if manifest.get("purpose") != SIGNATURE_PURPOSE:
        raise SignatureVerificationError("signature manifest purpose is not vendor qualification")
    if manifest.get("signature_kind") != "enterprise_pki":
        raise SignatureVerificationError("unsupported qualification signature kind")
    digest = _digest(manifest.get("attestation_sha256"), "attestation_sha256")
    if not compare_digest(digest, sha256(attestation).hexdigest()):
        raise SignatureVerificationError("signed attestation digest does not match")
    signed_at = _timestamp(manifest.get("signed_at"), "signed_at")
    signature_path = _contained_file(manifest_path.parent, manifest.get("signature_file"), "signature_file")
    certificate_path = _contained_file(manifest_path.parent, manifest.get("certificate_file"), "certificate_file")

    _exact_fields(
        policy,
        {"schema_version", "project_identities", "approved_signers"},
        "signature trust policy",
    )
    if policy.get("schema_version") != SIGNATURE_TRUST_POLICY_SCHEMA_VERSION:
        raise SignatureVerificationError("unsupported signature trust policy schema_version")
    project_identities = _strings(policy.get("project_identities"), "project_identities")
    signers = policy.get("approved_signers")
    if not isinstance(signers, list) or not signers:
        raise SignatureVerificationError("signature trust policy has no approved independent signers")

    executable = which("openssl")
    if executable is None:
        raise SignatureVerificationError("openssl is required for enterprise PKI signature verification")
    identity = _certificate_name(executable, certificate_path, "subject")
    issuer = _certificate_name(executable, certificate_path, "issuer")
    certificate_digest = _certificate_digest(executable, certificate_path)
    if identity in project_identities or issuer in project_identities:
        raise SignatureVerificationError("qualification signer or issuer is a project identity, not independent")

    approved: dict[str, Any] | None = None
    for candidate in signers:
        if not isinstance(candidate, dict):
            raise SignatureVerificationError("approved_signers entries must be objects")
        _exact_fields(
            candidate,
            {"kind", "identity", "issuer", "certificate_sha256", "trust_root"},
            "approved signer",
        )
        if (
            candidate.get("kind") == "enterprise_pki"
            and candidate.get("identity") == identity
            and candidate.get("issuer") == issuer
            and candidate.get("certificate_sha256") == certificate_digest
        ):
            approved = candidate
            break
    if approved is None:
        raise SignatureVerificationError("qualification certificate is not an approved independent signer")
    trust_root = _contained_file(
        trust_policy_path.parent,
        approved.get("trust_root"),
        "approved signer trust_root",
    )

    _run_openssl(
        (
            executable,
            "verify",
            "-purpose",
            "any",
            "-CAfile",
            str(trust_root),
            str(certificate_path),
        ),
        "qualification signer certificate is not trusted",
    )
    with TemporaryDirectory() as directory:
        public_key = Path(directory) / "signer-public-key.pem"
        try:
            extraction = subprocess.run(
                (executable, "x509", "-in", str(certificate_path), "-pubkey", "-noout"),
                capture_output=True,
                check=False,
                timeout=OPENSSL_TIMEOUT_SECONDS,
            )
        except subprocess.TimeoutExpired as exc:
            raise SignatureVerificationError("qualification public-key extraction timed out") from exc
        if extraction.returncode != 0 or not extraction.stdout:
            raise SignatureVerificationError("could not extract qualification signer public key")
        public_key.write_bytes(extraction.stdout)
        signing_payload = Path(directory) / "qualification-signing-payload.json"
        signing_payload.write_bytes(_signing_payload(digest, signed_at))
        _run_openssl(
            (
                executable,
                "dgst",
                "-sha256",
                "-verify",
                str(public_key),
                "-signature",
                str(signature_path),
                str(signing_payload),
            ),
            "qualification detached signature verification failed",
        )
    return VerifiedQualificationSignature(
        "enterprise_pki",
        identity,
        issuer,
        certificate_digest,
        sha256(manifest_raw).hexdigest(),
        signed_at,
    )


def qualification_signing_payload(
    attestation_path: Path,
    signed_at: str,
) -> bytes:
    """Return the canonical statement bytes that an independent party signs."""

    timestamp = _timestamp(signed_at, "signed_at")
    digest = sha256(_attestation_bytes(attestation_path)).hexdigest()
    return _signing_payload(digest, timestamp)


def _signing_payload(digest: str, signed_at: str) -> bytes:
    statement = {
        "schema_version": SIGNATURE_MANIFEST_SCHEMA_VERSION,
        "purpose": SIGNATURE_PURPOSE,
        "signature_kind": "enterprise_pki",
        "attestation_sha256": digest,
        "signed_at": signed_at,
    }
    return json.dumps(statement, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _read_document(path: Path, label: str) -> tuple[bytes, dict[str, Any]]:
    raw = path.read_bytes()
    if len(raw) > MAX_SIGNATURE_METADATA_BYTES:
        raise SignatureVerificationError(f"{label} exceeds {MAX_SIGNATURE_METADATA_BYTES} byte limit")
    try:
        value = json.loads(raw)
    except json.JSONDecodeError as exc:
        raise SignatureVerificationError(f"invalid {label} JSON: {exc}") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise SignatureVerificationError(f"{label} must be an object")
    return raw, value


def _attestation_bytes(path: Path) -> bytes:
    if not path.is_file():
        raise SignatureVerificationError("qualification attestation must be a regular file")
    if path.stat().st_size > MAX_SIGNED_ATTESTATION_BYTES:
        raise SignatureVerificationError(f"qualification attestation exceeds {MAX_SIGNED_ATTESTATION_BYTES} byte limit")
    return path.read_bytes()


def _exact_fields(value: dict[str, Any], fields: set[str], label: str) -> None:
    if set(value) != fields:
        raise SignatureVerificationError(f"{label} contains unknown or missing fields")


def _contained_file(root: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value or Path(value).is_absolute():
        raise SignatureVerificationError(f"{label} must be a relative file path")
    resolved_root = root.resolve()
    resolved = (root / value).resolve()
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise SignatureVerificationError(f"{label} must resolve to a regular file within {root}")
    if resolved.stat().st_size > MAX_SIGNATURE_ASSET_BYTES:
        raise SignatureVerificationError(f"{label} exceeds {MAX_SIGNATURE_ASSET_BYTES} byte limit")
    return resolved


def _certificate_name(executable: str, certificate: Path, field: str) -> str:
    try:
        result = subprocess.run(
            (executable, "x509", "-in", str(certificate), "-noout", f"-{field}", "-nameopt", "RFC2253"),
            capture_output=True,
            text=True,
            check=False,
            timeout=OPENSSL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SignatureVerificationError(f"qualification certificate {field} extraction timed out") from exc
    prefix = f"{field}="
    text = result.stdout.strip()
    if result.returncode != 0 or not text.startswith(prefix):
        raise SignatureVerificationError(f"could not read qualification certificate {field}")
    return text[len(prefix) :]


def _certificate_digest(executable: str, certificate: Path) -> str:
    try:
        result = subprocess.run(
            (executable, "x509", "-in", str(certificate), "-outform", "DER"),
            capture_output=True,
            check=False,
            timeout=OPENSSL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SignatureVerificationError("qualification certificate normalization timed out") from exc
    if result.returncode != 0 or not result.stdout:
        raise SignatureVerificationError("could not normalize qualification signer certificate")
    return sha256(result.stdout).hexdigest()


def _run_openssl(command: tuple[str, ...], failure: str) -> None:
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            check=False,
            timeout=OPENSSL_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SignatureVerificationError(f"{failure}: openssl timed out") from exc
    if result.returncode != 0:
        raise SignatureVerificationError(failure)


def _digest(value: Any, label: str) -> str:
    if not isinstance(value, str) or not _SHA256.fullmatch(value):
        raise SignatureVerificationError(f"{label} must be a lowercase SHA-256 digest")
    return value


def _timestamp(value: Any, label: str) -> str:
    if not isinstance(value, str):
        raise SignatureVerificationError(f"{label} must be an ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise SignatureVerificationError(f"{label} must be an ISO-8601 timestamp") from exc
    if parsed.tzinfo is None:
        raise SignatureVerificationError(f"{label} must include a timezone")
    return value


def _strings(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value or not all(isinstance(item, str) and item for item in value):
        raise SignatureVerificationError(f"{label} must be a non-empty list of non-empty strings")
    return value
