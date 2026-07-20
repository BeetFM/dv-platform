import json
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.core.models import EvidenceKind
from dv_platform.enterprise.semantics import SemanticImportError, SemanticManifestImporter


class SemanticManifestImporterTests(TestCase):
    def test_imports_complete_systemverilog_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            manifest = root / "bridge.dvsem.json"
            manifest.write_text(json.dumps(_manifest("bridge.sv")), encoding="utf-8")

            result = SemanticManifestImporter().import_semantics(manifest, root, strict=True)

        self.assertTrue(result.complete)
        module = result.modules[0]
        self.assertEqual(module.ports, ("clk", "rst_n", "valid", "ready"))
        self.assertEqual(module.parameter_details[0].default_value, "8")
        self.assertEqual(module.instance_details[0].connections[0].port_name, "clk")
        self.assertEqual(module.assignment_details[0].rhs_signals, ("valid", "ready"))
        self.assertEqual(module.control_domains[0].reset, "rst_n")
        self.assertEqual(module.protocols[0].kind, "ready_valid")
        self.assertEqual(module.ast_refs[0].kind, EvidenceKind.SEMANTIC_MANIFEST)

    def test_strict_mode_rejects_partial_semantics(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            document = _manifest("bridge.sv")
            document["modules"][0]["completeness"]["types"] = "partial"
            path = root / "bridge.semantic.json"
            path.write_text(json.dumps(document), encoding="utf-8")

            with self.assertRaisesRegex(SemanticImportError, "complete capability ledgers"):
                SemanticManifestImporter().import_semantics(path, root, strict=True)
            self.assertFalse(SemanticManifestImporter().import_semantics(path, root).complete)

    def test_rejects_unknown_fields_unsafe_sources_and_future_schemas(self) -> None:
        cases = (
            ({**_manifest("bridge.sv"), "guess": True}, "unknown fields"),
            (_manifest("../outside.sv"), "escapes repository root"),
            ({**_manifest("bridge.sv"), "schema_version": 99}, "newer than supported"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            for index, (document, message) in enumerate(cases):
                path = root / f"case-{index}.dvsem.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(index=index), self.assertRaisesRegex(SemanticImportError, message):
                    SemanticManifestImporter().import_semantics(path, root)

    def test_migrates_v0_as_explicitly_partial(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "legacy.vhd").write_text("entity legacy is end;\n", encoding="utf-8")
            module = _manifest("legacy.vhd")["modules"][0]
            module["language"] = "vhdl"
            module["standard"] = "1076-2019"
            module.pop("completeness")
            path = root / "legacy.semantic.json"
            path.write_text(
                json.dumps(
                    {
                        "producer": {"name": "legacy", "version": "1"},
                        "design_units": [module],
                    }
                ),
                encoding="utf-8",
            )

            result = SemanticManifestImporter().import_semantics(path, root)

        self.assertFalse(result.complete)
        self.assertEqual(result.completeness[0].language, "vhdl")

    def test_rejects_duplicate_and_dangling_semantic_identity(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "bridge.sv").write_text("module bridge; endmodule\n", encoding="utf-8")
            duplicate = _manifest("bridge.sv")
            duplicate["modules"][0]["ports"].append({"name": "clk", "direction": "input"})
            dangling = _manifest("bridge.sv")
            dangling["modules"][0]["memory_accesses"] = [{"access_id": "read", "memory": "missing", "kind": "read"}]
            for index, (document, message) in enumerate(((duplicate, "duplicate port"), (dangling, "unknown memory"))):
                path = root / f"identity-{index}.dvsem.json"
                path.write_text(json.dumps(document), encoding="utf-8")
                with self.subTest(index=index), self.assertRaisesRegex(SemanticImportError, message):
                    SemanticManifestImporter().import_semantics(path, root)

    def test_accepts_complete_verilog_and_vhdl_language_ledgers(self) -> None:
        cases = (
            ("verilog", "1364-2005", "module", "design.v"),
            ("vhdl", "1076-2019", "entity", "design.vhd"),
        )
        with TemporaryDirectory() as directory:
            root = Path(directory)
            for language, standard, kind, filename in cases:
                (root / filename).write_text("-- external analyzer input\n", encoding="utf-8")
                document = _manifest(filename)
                module = document["modules"][0]
                module["language"] = language
                module["standard"] = standard
                module["design_unit_kind"] = kind
                module["semantic_features"] = [{"kind": "process" if language == "vhdl" else "always"}]
                path = root / f"{language}.dvsem.json"
                path.write_text(json.dumps(document), encoding="utf-8")

                with self.subTest(language=language):
                    result = SemanticManifestImporter().import_semantics(path, root, strict=True)
                    self.assertTrue(result.complete)
                    self.assertEqual(result.completeness[0].standard, standard)


def _manifest(source: str) -> dict:
    categories = (
        "lexical_preprocessing",
        "libraries_compilation_units",
        "design_units",
        "declarations",
        "types",
        "expressions",
        "statements",
        "subprograms",
        "hierarchy",
        "elaboration",
        "parameters_generics",
        "ports",
        "packages_imports",
        "interfaces_modports",
        "classes_randomization",
        "assignments",
        "processes",
        "assertions",
        "functional_coverage",
        "generates",
        "memories",
        "timing_specify",
        "foreign_interfaces",
        "attributes_pragmas",
        "file_io",
        "clocks_resets",
        "cdc",
        "protocols",
    )
    return {
        "schema_version": 2,
        "producer": {"name": "enterprise-analyzer", "version": "2026.1"},
        "diagnostics": [],
        "modules": [
            {
                "name": "bridge",
                "language": "systemverilog",
                "standard": "1800-2023",
                "source": source,
                "completeness": {category: "complete" for category in categories},
                "ports": [
                    {"name": "clk", "direction": "input"},
                    {"name": "rst_n", "direction": "input"},
                    {"name": "valid", "direction": "input"},
                    {"name": "ready", "direction": "output"},
                ],
                "parameters": [{"name": "WIDTH", "default_value": "8"}],
                "types": [{"type_id": "logic8", "name": "data_t", "kind": "logic", "width": 8}],
                "memories": [],
                "memory_accesses": [],
                "clocks": [{"name": "clk", "direction": "input"}],
                "resets": [{"name": "rst_n", "direction": "input", "active_low": True}],
                "semantic_features": [
                    {
                        "kind": "always_ff",
                        "generation_supported": True,
                        "supported_targets": ["formal", "systemverilog"],
                    }
                ],
                "instances": [
                    {
                        "name": "u_child",
                        "module_name": "child",
                        "connections": [{"port_name": "clk", "direction": "input", "signal_refs": ["clk"]}],
                    }
                ],
                "continuous_assignments": [
                    {
                        "kind": "continuous",
                        "summary": "ready = valid",
                        "lhs_signals": ["ready"],
                        "rhs_signals": ["valid", "ready"],
                        "expressions": [
                            {
                                "kind": "binary",
                                "value": "&&",
                                "children": [
                                    {"kind": "reference", "name": "valid"},
                                    {"kind": "reference", "name": "ready"},
                                ],
                            }
                        ],
                    }
                ],
                "procedural_blocks": [
                    {
                        "kind": "always_ff",
                        "signal_refs": ["clk", "rst_n"],
                        "domain_id": "main",
                        "patterns": [{"kind": "hold", "target": "ready"}],
                    }
                ],
                "assertions": ["valid |-> ready"],
                "covers": ["valid && ready"],
                "generate_scopes": [],
                "imports": ["work.types_pkg"],
                "control_domains": [
                    {
                        "domain_id": "main",
                        "clock": "clk",
                        "reset": "rst_n",
                        "reset_active_low": True,
                        "asynchronous_reset": True,
                    }
                ],
                "cdc_paths": [],
                "protocols": [
                    {
                        "protocol_id": "rv",
                        "kind": "ready_valid",
                        "name": "stream",
                        "role": "sink",
                        "valid": "valid",
                        "ready": "ready",
                        "clock": "clk",
                        "reset": "rst_n",
                    }
                ],
                "documentation_refs": ["SPEC-1"],
            }
        ],
    }
