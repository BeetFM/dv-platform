import json
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.core.config import default_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.core.plugins import load_adapter_plugins
from dv_platform.core.security import append_audit_event, audit_file_mode, redact_text


class _Adapter:
    api_version = 1
    kind = "report_exporter"


class _EntryPoint:
    name = "company_report"
    group = "dv_platform.report_exporter"

    def load(self):
        return _Adapter


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

    def test_adapter_plugins_are_explicit_and_versioned(self) -> None:
        configured = (AdapterPluginConfig("report_exporter", "company_report", 1),)

        loaded = load_adapter_plugins(configured, (_EntryPoint(),))

        self.assertEqual(
            tuple((plugin.kind, plugin.name) for plugin in loaded), (("report_exporter", "company_report"),)
        )
        self.assertIsInstance(loaded[0].adapter, _Adapter)

    def test_adapter_plugins_reject_api_mismatch(self) -> None:
        configured = (AdapterPluginConfig("report_exporter", "company_report", 2),)

        with self.assertRaisesRegex(TypeError, "API mismatch"):
            load_adapter_plugins(configured, (_EntryPoint(),))


if __name__ == "__main__":
    unittest.main()
