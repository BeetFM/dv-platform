import json
import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.rtl import VerilatorRunResult, write_verilator_failure_summary
from dv_platform.core.config import default_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.core.plugins import load_adapter_plugins
from dv_platform.core.security import (
    EnvironmentSecretProvider,
    append_audit_event,
    audit_file_mode,
    redact_text,
    validate_export_destination,
    write_support_bundle,
)


class _Adapter:
    api_version = 1
    kind = "report_exporter"


class _EntryPoint:
    name = "company_report"
    group = "dv_platform.report_exporter"
    distribution_name = "company-dv-plugin"
    publisher = "Acme Verification"
    package_sha256 = "a" * 64

    def load(self):
        return _Adapter


class _AdapterV2:
    api_version = 2
    kind = "report_exporter"
    sandbox_aware = True
    audit_schema_version = 1


class _EntryPointV2(_EntryPoint):
    name = "company_report_v2"

    def load(self):
        return _AdapterV2


class SecurityAndPluginTests(unittest.TestCase):
    def test_audit_events_are_owner_only_and_redacted(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = replace(default_config(Path(temp_dir)), redact_patterns=(r"token=[^ ]+",))

            path = append_audit_event(config, "test", {"command": "tool token=secret other"})

            self.assertIsNotNone(path)
            assert path is not None
            self.assertEqual(audit_file_mode(path), 0o600)
            payload = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(payload["details"]["command"], "tool [REDACTED] other")
            self.assertNotIn("secret", path.read_text(encoding="utf-8"))
            self.assertEqual(redact_text(config, "token=another"), "[REDACTED]")

    def test_audit_event_repairs_existing_file_permissions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            config = default_config(Path(temp_dir))
            audit_path = config.work_dir / "audit" / "events.jsonl"
            audit_path.parent.mkdir(parents=True)
            audit_path.write_text("", encoding="utf-8")
            os.chmod(audit_path, 0o644)

            append_audit_event(config, "test", {})

            self.assertEqual(audit_file_mode(audit_path), 0o600)

    def test_verilator_failure_summary_redacts_command_records(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = replace(default_config(repo), redact_patterns=(r"token=[^ ]+",))
            stdout_log = repo / "stdout.log"
            stderr_log = repo / "stderr.log"
            version_log = repo / "version.log"
            stdout_log.write_text("tool [REDACTED]\n", encoding="utf-8")
            stderr_log.write_text("", encoding="utf-8")
            version_log.write_text("Verilator 5.0\n", encoding="utf-8")
            result = VerilatorRunResult(
                command=("wrapper", "token=secret"),
                return_code=1,
                stdout_log=stdout_log,
                stderr_log=stderr_log,
                version="Verilator 5.0",
                version_log=version_log,
                xml_files=(),
            )

            path = write_verilator_failure_summary(config, result)

            payload = path.read_text(encoding="utf-8")
            self.assertIn("[REDACTED]", payload)
            self.assertNotIn("secret", payload)

    def test_environment_secret_provider_and_export_allowlist_fail_closed(self) -> None:
        provider = EnvironmentSecretProvider({"DV_TOKEN": "secret"})
        self.assertEqual(provider.get("DV_TOKEN"), "secret")
        with self.assertRaises(ValueError):
            provider.get("../TOKEN")

        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = replace(default_config(root), export_roots=(root / "exports",))
            allowed = validate_export_destination(config, root / "exports" / "report.json")
            self.assertEqual(allowed, root / "exports" / "report.json")
            with self.assertRaisesRegex(ValueError, "outside configured"):
                validate_export_destination(config, root / "other" / "report.json")

    def test_support_bundle_contains_no_log_content_or_customer_paths(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            config = default_config(root)
            log = config.work_dir / "runs" / "customer-module" / "tool.log"
            log.parent.mkdir(parents=True)
            log.write_text("token=customer-secret\n", encoding="utf-8")

            path = write_support_bundle(config, {"schemas": {"plans": {"status": "current"}}, "summary": {}})

            payload = path.read_text(encoding="utf-8")
            self.assertNotIn("customer-secret", payload)
            self.assertNotIn("customer-module", payload)
            document = json.loads(payload)
            self.assertEqual(document["product"], "Veriforge")
            self.assertEqual(document["log_digests"][0]["bytes"], len("token=customer-secret\n"))

    def test_adapter_plugins_are_explicit_and_versioned(self) -> None:
        configured = (
            AdapterPluginConfig(
                "report_exporter",
                "company_report",
                1,
                publisher="Acme Verification",
                package_sha256="a" * 64,
                signature_kind="sigstore",
                signature_path="bundle.json",
                certificate_identity="release@acme.example",
                certificate_issuer="https://issuer.example",
            ),
        )

        verified = []
        loaded = load_adapter_plugins(
            configured,
            (_EntryPoint(),),
            approved_publishers=("Acme Verification",),
            signature_verifier=lambda distribution, digest, _config: verified.append((distribution, digest)),
        )

        self.assertEqual(
            tuple((plugin.kind, plugin.name) for plugin in loaded), (("report_exporter", "company_report"),)
        )
        self.assertIsInstance(loaded[0].adapter, _Adapter)
        self.assertEqual(verified, [("company-dv-plugin", "a" * 64)])

    def test_adapter_plugins_reject_api_mismatch(self) -> None:
        configured = (
            AdapterPluginConfig(
                "report_exporter",
                "company_report",
                2,
                publisher="Acme Verification",
                package_sha256="a" * 64,
                signature_kind="sigstore",
                signature_path="bundle.json",
                certificate_identity="release@acme.example",
                certificate_issuer="https://issuer.example",
            ),
        )

        with self.assertRaisesRegex(TypeError, "API mismatch"):
            load_adapter_plugins(
                configured,
                (_EntryPoint(),),
                approved_publishers=("Acme Verification",),
                signature_verifier=lambda *_args: None,
            )

    def test_adapter_api_v2_requires_sandbox_and_audit_contracts(self) -> None:
        configured = AdapterPluginConfig(
            "report_exporter",
            "company_report_v2",
            2,
            publisher="Acme Verification",
            package_sha256="a" * 64,
            signature_kind="sigstore",
            signature_path="bundle.json",
            certificate_identity="release@acme.example",
            certificate_issuer="https://issuer.example",
        )
        loaded = load_adapter_plugins(
            (configured,),
            (_EntryPointV2(),),
            approved_publishers=("Acme Verification",),
            signature_verifier=lambda *_args: None,
        )
        self.assertEqual(loaded[0].api_version, 2)

        class UnsafeAdapterV2:
            api_version = 2
            kind = "report_exporter"
            sandbox_aware = False
            audit_schema_version = 1

        entry = _EntryPointV2()
        entry.load = lambda: UnsafeAdapterV2
        with self.assertRaisesRegex(TypeError, "sandbox_aware"):
            load_adapter_plugins(
                (configured,),
                (entry,),
                approved_publishers=("Acme Verification",),
                signature_verifier=lambda *_args: None,
            )

    def test_adapter_plugins_reject_untrusted_code_before_loading(self) -> None:
        entry_point = _EntryPoint()
        configured = (AdapterPluginConfig("report_exporter", "company_report", 1),)

        with self.assertRaisesRegex(TypeError, "requires publisher and package_sha256"):
            load_adapter_plugins(configured, (entry_point,))

        wrong_hash = (
            AdapterPluginConfig(
                "report_exporter",
                "company_report",
                1,
                publisher="Acme Verification",
                package_sha256="b" * 64,
            ),
        )
        with self.assertRaisesRegex(TypeError, "package hash mismatch"):
            load_adapter_plugins(wrong_hash, (entry_point,), approved_publishers=("Acme Verification",))

        unsigned = (
            AdapterPluginConfig(
                "report_exporter",
                "company_report",
                publisher="Acme Verification",
                package_sha256="a" * 64,
            ),
        )
        with self.assertRaisesRegex(TypeError, "requires Sigstore or enterprise PKI"):
            load_adapter_plugins(unsigned, (entry_point,), approved_publishers=("Acme Verification",))


if __name__ == "__main__":
    unittest.main()
