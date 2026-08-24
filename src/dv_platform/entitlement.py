"""Closed, offline X.509 ECDSA-P256 entitlement verification."""

from __future__ import annotations

import base64
import json
import re
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path
from shutil import which
from tempfile import TemporaryDirectory
from typing import Any

SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 1024 * 1024
MAX_LIFETIME = timedelta(days=30)
GRACE_PERIOD = timedelta(hours=72)
_DIGEST = re.compile(r"^[0-9a-f]{64}$")
_CAPABILITY = re.compile(r"^[a-z][a-z0-9]*(?:[._-][a-z0-9]+)*$")
_FIELDS = {
    "schema_version",
    "organization",
    "plan",
    "capabilities",
    "concurrency_limit",
    "issued_at",
    "not_before",
    "expires_at",
    "issuer",
    "key_id",
    "certificate_sha256",
    "signature",
}


class EntitlementError(ValueError):
    code = "DV-ENTITLEMENT-INVALID"

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"{self.code}: {reason}")


@dataclass(frozen=True)
class VerifiedEntitlement:
    organization: str
    plan: str
    capabilities: frozenset[str]
    concurrency_limit: int
    state: str
    expires_at: datetime
    issuer: str
    key_id: str
    payload_sha256: str
    diagnostics: tuple[str, ...] = ()


def canonical_entitlement_payload(document: dict[str, Any]) -> bytes:
    """Canonical bytes signed by the issuer; signature is deliberately excluded."""

    payload = {key: value for key, value in document.items() if key != "signature"}
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("ascii")


def verify_entitlement(
    entitlement_path: Path,
    trust_policy_path: Path,
    *,
    expected_organization: str | None = None,
    now: datetime | None = None,
    revoked_keys: Iterable[str] = (),
) -> VerifiedEntitlement:
    document = _document(entitlement_path, "entitlement")
    policy = _document(trust_policy_path, "entitlement trust policy")
    values = _validate_document(document)
    issuer = _trusted_issuer(policy, values["issuer"], values["key_id"], values["certificate_sha256"])
    if values["key_id"] in set(revoked_keys) or values["key_id"] in set(policy.get("revoked_key_ids", [])):
        raise EntitlementError("entitlement signing key is revoked")
    if expected_organization is not None and values["organization"] != expected_organization:
        raise EntitlementError("entitlement organization does not match the configured organization")
    _verify_signature(document, trust_policy_path.parent, issuer)
    current = (now or datetime.now(UTC)).astimezone(UTC)
    if current < values["not_before"]:
        raise EntitlementError("entitlement is not yet valid")
    if current > values["expires_at"] + GRACE_PERIOD:
        raise EntitlementError("entitlement is expired")
    state = "grace" if current > values["expires_at"] else "valid"
    diagnostics = ("entitlement expired; audited grace period active",) if state == "grace" else ()
    return VerifiedEntitlement(
        values["organization"],
        values["plan"],
        frozenset(values["capabilities"]),
        values["concurrency_limit"],
        state,
        values["expires_at"],
        values["issuer"],
        values["key_id"],
        sha256(canonical_entitlement_payload(document)).hexdigest(),
        diagnostics,
    )


def _document(path: Path, label: str) -> dict[str, Any]:
    if not path.is_file() or path.stat().st_size > MAX_DOCUMENT_BYTES:
        raise EntitlementError(f"{label} is missing or exceeds the size limit")
    try:
        value = json.loads(path.read_bytes())
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise EntitlementError(f"{label} is not valid UTF-8 JSON") from exc
    if not isinstance(value, dict) or not all(isinstance(key, str) for key in value):
        raise EntitlementError(f"{label} must be an object")
    return value


def _validate_document(document: dict[str, Any]) -> dict[str, Any]:
    if set(document) != _FIELDS or document.get("schema_version") != SCHEMA_VERSION:
        raise EntitlementError("entitlement has unknown, missing, or unsupported fields")
    text_fields = ("organization", "plan", "issuer", "key_id")
    if any(not isinstance(document.get(key), str) or not document[key].strip() for key in text_fields):
        raise EntitlementError("entitlement identity fields must be non-empty strings")
    capabilities = document.get("capabilities")
    if (
        not isinstance(capabilities, list)
        or not capabilities
        or len(capabilities) != len(set(capabilities))
        or any(not isinstance(item, str) or not _CAPABILITY.fullmatch(item) for item in capabilities)
    ):
        raise EntitlementError("capabilities must be unique closed identifiers")
    concurrency = document.get("concurrency_limit")
    if type(concurrency) is not int or not 1 <= concurrency <= 10000:
        raise EntitlementError("concurrency_limit must be within 1..10000")
    issued = _time(document.get("issued_at"), "issued_at")
    not_before = _time(document.get("not_before"), "not_before")
    expires = _time(document.get("expires_at"), "expires_at")
    if not_before < issued or expires <= not_before or expires - issued > MAX_LIFETIME:
        raise EntitlementError("entitlement time bounds are invalid or exceed 30 days")
    certificate_digest = document.get("certificate_sha256")
    if not isinstance(certificate_digest, str) or not _DIGEST.fullmatch(certificate_digest):
        raise EntitlementError("certificate_sha256 is invalid")
    encoded_signature = document.get("signature")
    if not isinstance(encoded_signature, str):
        raise EntitlementError("signature is not canonical base64")
    try:
        signature = base64.b64decode(encoded_signature, validate=True)
    except (TypeError, ValueError) as exc:
        raise EntitlementError("signature is not canonical base64") from exc
    if not signature:
        raise EntitlementError("signature is empty")
    return {
        **document,
        "issued_at": issued,
        "not_before": not_before,
        "expires_at": expires,
    }


def _trusted_issuer(policy: dict[str, Any], issuer: str, key_id: str, certificate_digest: str) -> dict[str, str]:
    if set(policy) != {"schema_version", "issuers", "revoked_key_ids"} or policy.get("schema_version") != 1:
        raise EntitlementError("entitlement trust policy is not closed schema version 1")
    if not isinstance(policy.get("revoked_key_ids"), list):
        raise EntitlementError("revoked_key_ids must be a list")
    issuers = policy.get("issuers")
    if not isinstance(issuers, list):
        raise EntitlementError("issuers must be a list")
    for candidate in issuers:
        if (
            isinstance(candidate, dict)
            and set(candidate) == {"issuer", "key_id", "certificate_sha256", "certificate_file", "trust_root"}
            and candidate.get("issuer") == issuer
            and candidate.get("key_id") == key_id
            and candidate.get("certificate_sha256") == certificate_digest
        ):
            return candidate
    raise EntitlementError("entitlement issuer, key, or certificate is not trusted")


def _verify_signature(document: dict[str, Any], root: Path, issuer: dict[str, str]) -> None:
    executable = which("openssl")
    if executable is None:
        raise EntitlementError("openssl is required for offline entitlement verification")
    certificate = _contained(root, issuer["certificate_file"])
    trust_root = _contained(root, issuer["trust_root"])
    actual_digest = sha256(certificate.read_bytes()).hexdigest()
    if actual_digest != document["certificate_sha256"]:
        raise EntitlementError("entitlement certificate digest does not match")
    verify = subprocess.run(
        (executable, "verify", "-purpose", "any", "-CAfile", str(trust_root), str(certificate)),
        capture_output=True,
        check=False,
        timeout=30,
    )
    if verify.returncode:
        raise EntitlementError("entitlement certificate chain is not trusted")
    certificate_details = subprocess.run(
        (executable, "x509", "-in", str(certificate), "-noout", "-text"),
        capture_output=True,
        text=True,
        check=False,
        timeout=30,
    )
    details = certificate_details.stdout
    if (
        certificate_details.returncode
        or "id-ecPublicKey" not in details
        or ("prime256v1" not in details and "P-256" not in details)
        or "ecdsa-with-SHA256" not in details
    ):
        raise EntitlementError("entitlement certificate must use ECDSA P-256 with SHA-256")
    with TemporaryDirectory() as directory:
        public_key = Path(directory) / "public.pem"
        payload = Path(directory) / "payload.json"
        signature = Path(directory) / "signature.der"
        extracted = subprocess.run(
            (executable, "x509", "-in", str(certificate), "-pubkey", "-noout"),
            capture_output=True,
            check=False,
            timeout=30,
        )
        if extracted.returncode:
            raise EntitlementError("could not extract entitlement public key")
        public_key.write_bytes(extracted.stdout)
        payload.write_bytes(canonical_entitlement_payload(document))
        signature.write_bytes(base64.b64decode(document["signature"], validate=True))
        checked = subprocess.run(
            (executable, "dgst", "-sha256", "-verify", str(public_key), "-signature", str(signature), str(payload)),
            capture_output=True,
            check=False,
            timeout=30,
        )
        if checked.returncode:
            raise EntitlementError("entitlement signature verification failed")


def _contained(root: Path, value: str) -> Path:
    path = (root / value).resolve()
    if Path(value).is_absolute() or not path.is_relative_to(root.resolve()) or not path.is_file():
        raise EntitlementError("trust material must be a contained regular file")
    return path


def _time(value: Any, label: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EntitlementError(f"{label} must be a UTC RFC3339 timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EntitlementError(f"{label} is invalid") from exc
    if parsed.microsecond:
        raise EntitlementError(f"{label} must not contain fractional seconds")
    return parsed
