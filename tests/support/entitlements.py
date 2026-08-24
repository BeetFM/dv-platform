"""Repository-only entitlement PKI used by product-boundary tests."""

from __future__ import annotations

import base64
import json
import subprocess
from datetime import UTC, datetime, timedelta
from hashlib import sha256
from pathlib import Path

from dv_platform.domain.models import ProductConfig
from dv_platform.entitlement import canonical_entitlement_payload


def issue_test_entitlement(
    root: Path,
    capabilities: tuple[str, ...],
    *,
    organization: str = "test-organization",
    now: datetime | None = None,
) -> ProductConfig:
    """Create a short-lived non-production P-256 grant below ``root``."""

    fixture = root / "fixture-entitlement"
    fixture.mkdir(parents=True, exist_ok=True)
    key = fixture / "issuer-key.pem"
    certificate = fixture / "issuer-certificate.pem"
    _openssl("ecparam", "-name", "prime256v1", "-genkey", "-noout", "-out", str(key))
    _openssl(
        "req",
        "-new",
        "-x509",
        "-sha256",
        "-key",
        str(key),
        "-out",
        str(certificate),
        "-days",
        "2",
        "-subj",
        "/CN=dv-platform repository fixture issuer",
    )
    current = (now or datetime.now(UTC)).replace(microsecond=0)
    document = {
        "schema_version": 1,
        "organization": organization,
        "plan": "enterprise-test",
        "capabilities": list(capabilities),
        "concurrency_limit": 4,
        "issued_at": _timestamp(current - timedelta(minutes=1)),
        "not_before": _timestamp(current - timedelta(minutes=1)),
        "expires_at": _timestamp(current + timedelta(days=1)),
        "issuer": "repository-fixture",
        "key_id": "repository-fixture-p256-1",
        "certificate_sha256": sha256(certificate.read_bytes()).hexdigest(),
        "signature": "",
    }
    payload = fixture / "payload.json"
    signature = fixture / "signature.der"
    payload.write_bytes(canonical_entitlement_payload(document))
    _openssl("dgst", "-sha256", "-sign", str(key), "-out", str(signature), str(payload))
    document["signature"] = base64.b64encode(signature.read_bytes()).decode("ascii")
    entitlement = fixture / "entitlement.json"
    entitlement.write_text(json.dumps(document, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    trust = fixture / "trust-policy.json"
    trust.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "issuers": [
                    {
                        "issuer": document["issuer"],
                        "key_id": document["key_id"],
                        "certificate_sha256": document["certificate_sha256"],
                        "certificate_file": certificate.name,
                        "trust_root": certificate.name,
                    }
                ],
                "revoked_key_ids": [],
            },
            indent=2,
            sort_keys=True,
        )
        + "\n",
        encoding="utf-8",
    )
    return ProductConfig(
        organization=organization,
        entitlement_path=entitlement,
        trust_policy_path=trust,
        require_enterprise=True,
    )


def _timestamp(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _openssl(*arguments: str) -> None:
    subprocess.run(("openssl", *arguments), check=True, capture_output=True, timeout=30)
