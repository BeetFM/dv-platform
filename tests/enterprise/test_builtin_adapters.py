import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.docs import read_configured_document_index
from dv_platform.analysis.rtl import write_normalized_rtl_facts
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import AdapterPluginConfig, EvidenceKind, EvidenceRef, RTLModule
from dv_platform.core.plugins import load_adapter_plugins
from tests.support.entitlements import issue_test_entitlement


class BuiltinAdapterQualificationTests(unittest.TestCase):
    def test_all_local_adapter_boundaries_load_through_versioned_entry_points(self) -> None:
        configured = (
            AdapterPluginConfig("document_loader", "local_documents"),
            AdapterPluginConfig("document_loader", "ocr_sidecar"),
            AdapterPluginConfig("embedding_provider", "local_hash"),
            AdapterPluginConfig("vector_store", "local_json"),
            AdapterPluginConfig("report_exporter", "json_manifest"),
            AdapterPluginConfig("redaction_policy", "regex"),
        )

        loaded = load_adapter_plugins(configured)

        self.assertEqual(
            tuple((item.kind, item.name, item.api_version) for item in loaded),
            tuple((item.kind, item.name, 1) for item in configured),
        )

    def test_cli_indexes_governed_ocr_with_configured_embedding_and_store(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            docs = root / "docs"
            docs.mkdir()
            image = docs / "register-map.png"
            image.write_bytes(b"not-decoded-by-the-core")
            (docs / "register-map.png.ocr.txt").write_text(
                "CONTROL register resets to zero and is writable.\n", encoding="utf-8"
            )
            config = replace(
                default_config(root),
                product=issue_test_entitlement(root, ("adapter.enterprise", "cli.enterprise")),
                documentation_paths=(docs,),
                adapter_plugins=(
                    AdapterPluginConfig("document_loader", "ocr_sidecar"),
                    AdapterPluginConfig("embedding_provider", "local_hash"),
                    AdapterPluginConfig("vector_store", "local_json"),
                ),
            )
            write_config(config, root / "dv-platform.toml")

            output = StringIO()
            with redirect_stdout(output):
                result = main(["--repo-root", str(root), "index-docs"])

            self.assertEqual(result, 0, output.getvalue())
            chunks = read_configured_document_index(config)
            self.assertEqual(len(chunks), 1)
            self.assertEqual(chunks[0].source, image.resolve())
            self.assertIn("CONTROL register", chunks[0].text)
            vector_payload = json.loads((config.retrieval_index_dir / "vectors.json").read_text(encoding="utf-8"))
            self.assertEqual(vector_payload["embedding_model"], "local-hash-v1")

    def test_report_and_redaction_adapters_produce_deterministic_safe_output(self) -> None:
        configured = (
            AdapterPluginConfig("report_exporter", "json_manifest"),
            AdapterPluginConfig("redaction_policy", "regex"),
        )
        loaded = load_adapter_plugins(configured)
        exporter = loaded[0].adapter
        policy = loaded[1].adapter
        with TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "status.json"
            source.write_text('{"passed":true}\n', encoding="utf-8")
            output = root / "manifest.json"

            exporter.export((source,), output)

            first = output.read_bytes()
            exporter.export((source,), output)
            self.assertEqual(output.read_bytes(), first)
            payload = json.loads(first)
            self.assertEqual(payload["reports"][0]["path"], "status.json")
            self.assertEqual(policy.redact("token=secret", (r"token=[^ ]+",)), "[REDACTED]")

    def test_review_command_connects_configured_report_exporter(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                product=issue_test_entitlement(root, ("adapter.enterprise", "cli.enterprise")),
                adapter_plugins=(AdapterPluginConfig("report_exporter", "json_manifest"),),
            )
            write_config(config, root / "dv-platform.toml")
            write_normalized_rtl_facts(
                config,
                (
                    RTLModule(
                        "unit",
                        ast_refs=(EvidenceRef(EvidenceKind.VERILATOR_AST, "Vunit.xml", "module:unit"),),
                    ),
                ),
                verilator_version="Verilator 5.020",
            )

            output = StringIO()
            with redirect_stdout(output):
                result = main(["--repo-root", str(root), "review"])

            self.assertEqual(result, 0, output.getvalue())
            manifest = config.work_dir / "review" / "exports" / "json_manifest.json"
            self.assertTrue(manifest.is_file())
            self.assertEqual(len(json.loads(manifest.read_text(encoding="utf-8"))["reports"]), 2)


if __name__ == "__main__":
    unittest.main()
