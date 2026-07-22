"""Versioned entry-point loading for non-generator platform adapters."""

from __future__ import annotations

import hashlib
import os
import shutil
import subprocess
import tempfile
from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from pathlib import Path
from typing import Protocol, cast

from dv_platform.core.models import AdapterPluginConfig

ADAPTER_API_VERSIONS = (1, 2)


class SignatureVerifier(Protocol):
    def __call__(self, distribution: str, package_sha256: str, configured: AdapterPluginConfig) -> None: ...


@dataclass(frozen=True)
class LoadedAdapterPlugin:
    """One explicitly configured and API-compatible adapter plugin."""

    kind: str
    name: str
    api_version: int
    adapter: object


class _EntryPoint:
    name: str
    group: str

    def load(self) -> object:
        raise NotImplementedError


def load_adapter_plugins(
    configured: tuple[AdapterPluginConfig, ...],
    entry_points: object | None = None,
    approved_publishers: tuple[str, ...] = (),
    signature_verifier: SignatureVerifier | None = None,
) -> tuple[LoadedAdapterPlugin, ...]:
    """Load explicitly enabled, trusted adapters and enforce API version."""

    if not configured:
        return ()
    discovered = metadata.entry_points() if entry_points is None else entry_points
    loaded: list[LoadedAdapterPlugin] = []
    for plugin in configured:
        group = f"dv_platform.{plugin.kind}"
        candidates = _entry_points_for_group(discovered, group)
        entry_point = next((item for item in candidates if str(item.name) == plugin.name), None)
        if entry_point is None:
            raise LookupError(f"Enabled adapter plugin was not found: {plugin.kind}/{plugin.name}")
        verify_entry_point_trust(entry_point, plugin, approved_publishers, signature_verifier=signature_verifier)
        adapter = entry_point.load()
        if isinstance(adapter, type):
            adapter = adapter()
        api_version = getattr(adapter, "api_version", None)
        if api_version != plugin.api_version or api_version not in ADAPTER_API_VERSIONS:
            raise TypeError(
                f"Adapter plugin API mismatch for {plugin.kind}/{plugin.name}: "
                f"configured={plugin.api_version}, provided={api_version}, supported={ADAPTER_API_VERSIONS}"
            )
        adapter_kind = getattr(adapter, "kind", plugin.kind)
        if adapter_kind != plugin.kind:
            raise TypeError(
                f"Adapter plugin kind mismatch for {plugin.name}: configured={plugin.kind}, provided={adapter_kind}"
            )
        if api_version == 2 and (
            getattr(adapter, "sandbox_aware", None) is not True or getattr(adapter, "audit_schema_version", None) != 1
        ):
            raise TypeError(
                "Adapter plugin API v2 requires sandbox_aware=true and audit_schema_version=1: "
                f"{plugin.kind}/{plugin.name}"
            )
        loaded.append(LoadedAdapterPlugin(plugin.kind, plugin.name, api_version, adapter))
    return tuple(loaded)


def verify_entry_point_trust(
    entry_point: object,
    configured: AdapterPluginConfig,
    approved_publishers: tuple[str, ...],
    *,
    signature_verifier: SignatureVerifier | None = None,
) -> None:
    """Reject third-party executable code before import unless identity and content are approved."""

    distribution_name, publisher, package_sha256 = _entry_point_identity(entry_point)
    if _canonical_name(distribution_name) == "dv-platform":
        return
    label = f"{configured.kind}/{configured.name}"
    if not distribution_name:
        raise TypeError(f"Third-party plugin distribution identity is unavailable: {label}")
    if configured.publisher is None or configured.package_sha256 is None:
        raise TypeError(f"Third-party plugin requires publisher and package_sha256: {label}")
    if configured.publisher not in approved_publishers:
        raise TypeError(f"Third-party plugin publisher is not approved: {label}/{configured.publisher}")
    if publisher != configured.publisher:
        raise TypeError(
            f"Third-party plugin publisher mismatch for {label}: configured={configured.publisher}, provided={publisher}"
        )
    if package_sha256 != configured.package_sha256:
        raise TypeError(f"Third-party plugin package hash mismatch for {label}")
    if configured.signature_kind is None:
        raise TypeError(f"Third-party plugin requires Sigstore or enterprise PKI verification: {label}")
    (signature_verifier or verify_plugin_signature)(distribution_name, package_sha256, configured)


def verify_plugin_signature(distribution: str, package_sha256: str, configured: AdapterPluginConfig) -> None:
    """Cryptographically verify a distribution digest statement before import."""

    statement = f"{distribution}\nsha256:{package_sha256}\n".encode()
    signature = Path(configured.signature_path or "").expanduser().resolve(strict=False)
    if not signature.is_file() or signature.is_symlink():
        raise TypeError(f"Plugin signature material is unavailable: {signature}")
    with tempfile.TemporaryDirectory(prefix="dv-plugin-trust-") as directory:
        payload = Path(directory) / "distribution-digest.txt"
        payload.write_bytes(statement)
        command: tuple[str, ...]
        if configured.signature_kind == "sigstore":
            executable = shutil.which("cosign")
            if executable is None:
                raise TypeError("cosign is required for Sigstore plugin verification")
            command = (
                executable,
                "verify-blob",
                "--bundle",
                str(signature),
                "--certificate-identity",
                configured.certificate_identity or "",
                "--certificate-oidc-issuer",
                configured.certificate_issuer or "",
                str(payload),
            )
        elif configured.signature_kind == "pki":
            executable = shutil.which("openssl")
            trust_root = Path(configured.trust_root or "").expanduser().resolve(strict=False)
            if executable is None or not trust_root.is_file() or trust_root.is_symlink():
                raise TypeError("openssl and a regular enterprise PKI trust root are required")
            command = (
                executable,
                "cms",
                "-verify",
                "-binary",
                "-inform",
                "DER",
                "-in",
                str(signature),
                "-content",
                str(payload),
                "-CAfile",
                str(trust_root),
                "-purpose",
                "any",
                "-out",
                os.devnull,
            )
        else:
            raise TypeError(f"Unsupported plugin signature kind: {configured.signature_kind}")
        try:
            result = subprocess.run(command, capture_output=True, timeout=30, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise TypeError(f"Plugin signature verification could not run: {exc}") from exc
        if result.returncode != 0:
            raise TypeError("Plugin signature verification failed")


def _entry_point_identity(entry_point: object) -> tuple[str, str, str]:
    distribution = getattr(entry_point, "dist", None)
    if distribution is None:
        return (
            str(getattr(entry_point, "distribution_name", "")),
            str(getattr(entry_point, "publisher", "")),
            str(getattr(entry_point, "package_sha256", "")),
        )
    distribution_name = str(getattr(distribution, "name", "") or distribution.metadata.get("Name", ""))
    publisher = str(
        distribution.metadata.get("Author-email", "")
        or distribution.metadata.get("Author", "")
        or distribution.metadata.get("Maintainer-email", "")
        or distribution.metadata.get("Maintainer", "")
    )
    digest = hashlib.sha256()
    files = sorted(
        (
            file
            for file in (distribution.files or ())
            if "__pycache__" not in file.parts and file.suffix not in {".pyc", ".pyo"}
        ),
        key=lambda item: str(item),
    )
    for file in files:
        path = distribution.locate_file(file)
        if not path.is_file():
            continue
        digest.update(str(file).encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return distribution_name, publisher, digest.hexdigest()


def _canonical_name(name: str) -> str:
    return name.lower().replace("_", "-").replace(".", "-")


def _entry_points_for_group(discovered: object, group: str) -> tuple[_EntryPoint, ...]:
    if hasattr(discovered, "select"):
        selected = discovered.select(group=group)
    elif isinstance(discovered, dict):
        selected = discovered.get(group, ())
    elif isinstance(discovered, Iterable):
        selected = tuple(item for item in discovered if getattr(item, "group", None) == group)
    else:
        selected = ()
    return tuple(cast(_EntryPoint, item) for item in selected)
