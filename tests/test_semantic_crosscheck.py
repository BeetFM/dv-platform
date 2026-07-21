import json
import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.semantic_crosscheck import (
    CAPABILITY_EXPRESSIONS,
    CORE_REQUIRED_CAPABILITIES,
    FrontendMetadata,
    NormalizedFactCrossChecker,
    SemanticCrossCheckResult,
    SlangAnalyzer,
    _modules_from_slang_json,
    _normalize_slang_document,
    benchmark_slang_normalization,
    write_crosscheck_result,
)
from dv_platform.core.models import RTLModule, RTLParameter, RTLPort


class SemanticCrossCheckTests(unittest.TestCase):
    def test_matching_normalized_facts_pass(self) -> None:
        module = RTLModule(
            name="top",
            original_name="top",
            ports=("bus",),
            port_details=(RTLPort("bus", "input", width=8),),
        )

        result = NormalizedFactCrossChecker().compare((module,), (module,))

        self.assertTrue(result.passed)
        self.assertEqual(result.checked_modules, ("top",))

    def test_port_disagreement_is_reported(self) -> None:
        primary = RTLModule(
            name="top",
            original_name="top",
            ports=("bus",),
            port_details=(RTLPort("bus", "input", width=8),),
        )
        reference = RTLModule(
            name="top",
            original_name="top",
            ports=("bus",),
            port_details=(RTLPort("bus", "input", width=16),),
        )

        result = NormalizedFactCrossChecker().compare((primary,), (reference,))

        self.assertFalse(result.passed)
        self.assertEqual(result.issues[0].field, "port_details")

    def test_missing_module_is_not_silently_accepted(self) -> None:
        module = RTLModule(name="top", original_name="top")

        result = NormalizedFactCrossChecker().compare((module,), ())

        self.assertFalse(result.passed)
        self.assertEqual(result.issues[0].field, "module")

    def test_slang_ast_json_is_normalized(self) -> None:
        modules = _modules_from_slang_json(
            {
                "design": {
                    "members": [
                        {
                            "kind": "InstanceBody",
                            "name": "top",
                            "source_file": "top.sv",
                            "members": [
                                {
                                    "kind": "Port",
                                    "name": "clk",
                                    "direction": "In",
                                    "type": {"kind": "ScalarType", "isSigned": False},
                                },
                                {
                                    "kind": "Port",
                                    "name": "data",
                                    "direction": "Out",
                                    "type": {"kind": "PackedArrayType", "range": "[7:0]"},
                                },
                                {"kind": "Instance", "name": "u_child", "body": {"name": "child"}},
                                {
                                    "kind": "ContinuousAssign",
                                    "source_file": "top.sv",
                                    "source_line": 12,
                                    "source_column": 5,
                                    "assignment": {
                                        "kind": "Assignment",
                                        "left": {"kind": "NamedValue", "symbol": "1 data"},
                                        "right": {"kind": "NamedValue", "symbol": "2 clk"},
                                    },
                                },
                            ],
                        }
                    ]
                }
            }
        )

        self.assertEqual(len(modules), 1)
        self.assertEqual(modules[0].ports, ("clk", "data"))
        self.assertEqual(modules[0].port_details[0].width, 1)
        self.assertEqual(modules[0].port_details[1].width, 8)
        self.assertEqual(modules[0].instances, ("u_child:child",))
        self.assertEqual(modules[0].assignment_details[0].lhs_signals, ("data",))
        self.assertEqual(modules[0].assignment_details[0].rhs_signals, ("clk",))

    def test_specializations_match_by_parameter_identity_not_insertion_order(self) -> None:
        width8 = RTLModule(
            "top8",
            original_name="top",
            parameter_details=(RTLParameter("WIDTH", "8"),),
        )
        width16 = RTLModule(
            "top16",
            original_name="top",
            parameter_details=(RTLParameter("WIDTH", "16"),),
        )

        result = NormalizedFactCrossChecker().compare((width8, width16), (width16, width8))

        self.assertTrue(result.passed)
        self.assertEqual(result.checked_modules, ("top[WIDTH=16]", "top[WIDTH=8]"))

    def test_repeated_slang_instance_bodies_are_not_collapsed(self) -> None:
        modules = _modules_from_slang_json(
            {
                "design": {
                    "members": [
                        {
                            "kind": "InstanceBody",
                            "name": "top_8",
                            "definitionName": "top",
                            "members": [{"kind": "Parameter", "name": "WIDTH", "value": "8"}],
                        },
                        {
                            "kind": "InstanceBody",
                            "name": "top_16",
                            "definitionName": "top",
                            "members": [{"kind": "Parameter", "name": "WIDTH", "value": "16"}],
                        },
                    ]
                }
            }
        )

        self.assertEqual(len(modules), 2)
        self.assertEqual({module.original_name for module in modules}, {"top"})
        self.assertEqual(
            {module.parameter_details[0].default_value for module in modules},
            {"8", "16"},
        )

    def test_missing_required_capability_is_an_error(self) -> None:
        module = RTLModule("top", original_name="top")
        result = NormalizedFactCrossChecker(
            reference_capabilities=CORE_REQUIRED_CAPABILITIES,
            required_capabilities=(*CORE_REQUIRED_CAPABILITIES, CAPABILITY_EXPRESSIONS),
        ).compare((module,), (module,))

        self.assertFalse(result.passed)
        issue = next(issue for issue in result.issues if issue.field == "capability")
        self.assertEqual(issue.capability, CAPABILITY_EXPRESSIONS)

    def test_crosscheck_artifact_is_versioned_and_auditable(self) -> None:
        result = SemanticCrossCheckResult(
            "verilator",
            "slang",
            ("top",),
            run_id="WIDTH_8",
            primary=FrontendMetadata("verilator", "5.020", ("verilator", "--xml-only")),
            reference=FrontendMetadata("slang", "11.0", ("slang", "--ast-json"), "ast.json"),
        )
        with TemporaryDirectory() as temp_dir:
            path = write_crosscheck_result(Path(temp_dir) / "result.json", result)
            payload = json.loads(path.read_text(encoding="utf-8"))

        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["run_id"], "WIDTH_8")
        self.assertEqual(payload["reference"]["artifact_path"], "ast.json")

    def test_slang_normalizes_sequential_property_generate_and_memory_facts(self) -> None:
        modules = _modules_from_slang_json(
            {
                "design": {
                    "members": [
                        {
                            "kind": "InstanceBody",
                            "name": "top",
                            "members": [
                                {
                                    "kind": "Variable",
                                    "name": "mem",
                                    "type": {
                                        "kind": "UnpackedArrayType",
                                        "width": 8,
                                        "unpackedDimensions": ["[3:0]"],
                                    },
                                },
                                {
                                    "kind": "GenerateBlock",
                                    "name": "g_enabled",
                                    "selected": True,
                                    "index": 2,
                                    "condition": {"kind": "IntegerLiteral", "value": "1"},
                                    "members": [],
                                },
                                {
                                    "kind": "ProceduralBlock",
                                    "procedureKind": "AlwaysFF",
                                    "timing": {
                                        "kind": "EventList",
                                        "events": [
                                            {
                                                "kind": "PosEdgeEvent",
                                                "expression": {"kind": "NamedValue", "symbol": "1 clk"},
                                            },
                                            {
                                                "kind": "NegEdgeEvent",
                                                "expression": {"kind": "NamedValue", "symbol": "2 rst_n"},
                                            },
                                        ],
                                    },
                                    "body": {
                                        "kind": "IfStatement",
                                        "condition": {"kind": "NamedValue", "symbol": "2 rst_n"},
                                        "ifTrue": {
                                            "kind": "Assignment",
                                            "isNonBlocking": True,
                                            "left": {"kind": "NamedValue", "symbol": "3 q"},
                                            "right": {"kind": "IntegerLiteral", "value": "0"},
                                        },
                                        "statements": [
                                            {
                                                "kind": "ConcurrentAssertionStatement",
                                                "name": "q_known",
                                                "property": {"kind": "NamedValue", "symbol": "3 q"},
                                            }
                                        ],
                                    },
                                },
                            ],
                        }
                    ]
                }
            }
        )

        module = modules[0]
        self.assertEqual(module.memories[0].depth, 4)
        self.assertEqual(module.generate_scopes[0].iteration_index, 2)
        self.assertTrue(module.generate_scopes[0].selected)
        self.assertEqual(module.control_domains[0].clock, "clk")
        self.assertEqual(module.control_domains[0].reset, "rst_n")
        self.assertTrue(module.control_domains[0].asynchronous_reset)
        self.assertEqual(module.assignment_details[0].kind, "nonblocking")
        self.assertEqual(module.assignment_details[0].lhs_signals, ("q",))
        self.assertEqual(module.property_details[0].name, "q_known")
        self.assertEqual(module.property_details[0].support_status, "normalized")

    def test_slang_runner_rejects_invalid_json_and_persists_diagnostics(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            tool_dir = root / "tool dir"
            tool_dir.mkdir()
            script = tool_dir / "fake slang.py"
            script.write_text(
                """import pathlib
import sys
if "--version" in sys.argv:
    print("slang 11.0.0 test")
    raise SystemExit(0)
path = pathlib.Path(sys.argv[sys.argv.index("--ast-json") + 1])
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text("{invalid", encoding="utf-8")
""",
                encoding="utf-8",
            )
            ast_path = root / "output dir" / "ast.json"
            result = SlangAnalyzer(f'{sys.executable} "{script}"').run((), ast_path)

            self.assertFalse(result.succeeded)
            self.assertIn("invalid", result.error or "")
            diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "invalid_ast")
            self.assertTrue(result.command_log.is_file())
            self.assertTrue(result.version_log.is_file())

    def test_slang_runner_rejects_compilation_failure_and_stale_ast(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "failing_slang.py"
            script.write_text(
                """import sys
if "--version" in sys.argv:
    print("slang 11.0.0 test")
    raise SystemExit(0)
print("synthetic compile failure", file=sys.stderr)
raise SystemExit(3)
""",
                encoding="utf-8",
            )
            ast_path = root / "slang" / "ast.json"
            ast_path.parent.mkdir()
            ast_path.write_text('{"stale": true}', encoding="utf-8")

            result = SlangAnalyzer(f"{sys.executable} {script}").run((), ast_path)

            self.assertFalse(result.succeeded)
            self.assertEqual(result.return_code, 3)
            self.assertFalse(ast_path.exists())
            self.assertIn("synthetic compile failure", result.stderr_log.read_text(encoding="utf-8"))

    def test_slang_runner_records_interrupted_process(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            script = root / "interrupted_slang.py"
            script.write_text(
                """import sys
if "--version" in sys.argv:
    print("slang 11.0.0 test")
    raise SystemExit(0)
print("interrupted", file=sys.stderr)
raise SystemExit(130)
""",
                encoding="utf-8",
            )

            result = SlangAnalyzer(f"{sys.executable} {script}").run((), root / "ast.json")

            self.assertFalse(result.succeeded)
            self.assertEqual(result.return_code, 130)
            diagnostics = json.loads(result.diagnostics_path.read_text(encoding="utf-8"))
            self.assertEqual(diagnostics["status"], "compilation_failed")
            self.assertIn("interrupted", diagnostics["diagnostics"])

    def test_unsupported_expression_withdraws_capability_with_location(self) -> None:
        _modules, capabilities, unsupported, reasons = _normalize_slang_document(
            {
                "design": {
                    "members": [
                        {
                            "kind": "InstanceBody",
                            "name": "top",
                            "members": [
                                {
                                    "kind": "ProceduralBlock",
                                    "body": {
                                        "kind": "NewClass",
                                        "source_file_start": "top.sv",
                                        "source_line_start": 9,
                                        "source_column_start": 4,
                                    },
                                }
                            ],
                        }
                    ]
                }
            }
        )

        self.assertNotIn(CAPABILITY_EXPRESSIONS, capabilities)
        self.assertIn(CAPABILITY_EXPRESSIONS, unsupported)
        self.assertIn("top.sv:9:4", dict(reasons)[CAPABILITY_EXPRESSIONS])

    def test_large_ast_normalization_stays_within_qualification_budget(self) -> None:
        document = {
            "design": {
                "members": [
                    {
                        "kind": "InstanceBody",
                        "name": "large_top",
                        "members": [
                            {
                                "kind": "Variable",
                                "name": f"signal_{index}",
                                "type": {"kind": "ScalarType", "isSigned": False},
                            }
                            for index in range(5_000)
                        ],
                    }
                ]
            }
        }

        result = benchmark_slang_normalization(document)

        self.assertGreater(result.nodes, 10_000)
        self.assertEqual(result.modules, 1)
        self.assertLess(result.elapsed_seconds, 5.0)
        self.assertLess(result.peak_bytes, 64 * 1024 * 1024)


if __name__ == "__main__":
    unittest.main()
