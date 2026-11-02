"""The RTL loop preserves contracts and selects only proven, measured improvements."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.core.config import default_config
from dv_platform.domain.models import AIConfig
from dv_platform.enterprise.rtl_optimization import run_rtl_optimization
from dv_platform.enterprise.rtl_physical import load_rtl_project
from dv_platform.physical_design import write_document
from tests.ai.test_physical_design import Client, analysis
from tests.ai.test_rtl import RTL_PROPOSAL
from tests.domain.test_physical_design import project_fixture
from tests.enterprise.test_enterprise_cli import _main
from tests.support.entitlements import issue_test_entitlement

BACKEND = "dv_platform.enterprise.rtl_optimization"


class RTLOptimizationTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        physical, manifest = project_fixture(self.root)
        manifest["inputs"].append("mapped.v")
        (self.root / "mapped.v").write_text("fixture")
        write_document(physical, manifest)
        (self.root / "top.sv").write_text("module top(input a, output y); assign y = a & a; endmodule\n")
        (self.root / "design.md").write_text("Output equals input in the same cycle.")
        self.project = self.root / "rtl-project.json"
        write_document(
            self.project,
            {
                "schema_version": 1,
                "design": "top",
                "sources": ["top.sv"],
                "documents": ["design.md"],
                "physical_project": "project.json",
                "mapping_library": "cells.lib",
                "netlist": "mapped.v",
                "objective": "area_um2",
            },
        )
        self.config = replace(
            default_config(self.root),
            allow_network=True,
            ai=AIConfig(model="fixture/rtl", allowed_stages=("rtl_optimization",)),
            product=issue_test_entitlement(self.root, ("cli.enterprise", "adapter.enterprise")),
        )

    def run_cases(self, metrics, proof="equivalent", replies=None, iterations=1):
        baseline = analysis()
        candidate = deepcopy(baseline)
        candidate["metrics"].update(metrics)
        measurements = [{"analysis": value, "run": "fixture-run"} for value in (baseline, candidate)]
        with (
            patch(f"{BACKEND}.lower_rtl_sources", return_value=self.root / "logical.v"),
            patch(f"{BACKEND}.measure_rtl", side_effect=measurements) as measure,
            patch(f"{BACKEND}.prove_rtl_candidate", return_value={"status": proof}),
        ):
            result = run_rtl_optimization(
                self.config, self.project, max_iterations=iterations, model_client=Client(replies or [RTL_PROPOSAL])
            )
        return result, measure

    def test_equivalent_measured_area_reduction_is_selected(self):
        record, measure = self.run_cases({"area_um2": 550})
        self.assertEqual(record["status"], "improved", record.get("error"))
        self.assertEqual(record["selected"], "candidate-1")
        self.assertFalse(record["signoff_approved"])
        self.assertEqual(measure.call_count, 2)
        self.assertEqual(measure.call_args.kwargs["reference"], Path(record["output"]) / "baseline-source/logical.v")
        self.assertIn("baseline/top.sv", measure.call_args.kwargs["rtl_inputs"])
        self.assertIn("decision/receipt.json", measure.call_args.kwargs["rtl_inputs"])
        self.assertIn("a & a", (self.root / "top.sv").read_text())
        self.assertEqual((self.root / "constraints.sdc").read_text(), "fixture\n")

    def test_timing_regression_rejects_smaller_area(self):
        record, _ = self.run_cases({"area_um2": 550, "setup_wns_ns": -0.1})
        self.assertEqual(record["selected"], "baseline")
        self.assertIn("setup_wns_ns", record["iterations"][0]["evaluation"]["regressions"])

    def test_failed_proof_never_reaches_physical_measurement(self):
        record, measure = self.run_cases({}, proof="rejected")
        self.assertEqual(measure.call_count, 1)
        self.assertEqual(record["selected"], "baseline")
        self.assertEqual(record["iterations"][0]["proof_status"], "rejected")

    def test_identical_area_is_not_an_improvement(self):
        record, _ = self.run_cases({})
        self.assertEqual(record["status"], "no_improvement")

    def test_rejected_experiment_is_supplied_to_next_decision(self):
        stop = {**RTL_PROPOSAL, "edits": None}
        record, measure = self.run_cases({}, proof="rejected", replies=[RTL_PROPOSAL, stop], iterations=2)
        self.assertEqual(len(record["iterations"]), 2)
        self.assertEqual(measure.call_count, 1)
        self.assertEqual(record["stop_reason"], "agent_stopped")

    def test_manifest_rejects_constraint_replacement(self):
        project = json.loads(self.project.read_text())
        project["netlist"] = "constraints.sdc"
        write_document(self.project, project)
        with self.assertRaisesRegex(ValueError, "unprotected"):
            load_rtl_project(self.project)

    def test_source_scope_and_resource_budget_are_closed_project_inputs(self):
        project = json.loads(self.project.read_text())
        for fields in (
            {"editable_sources": ["design.md"]},
            {"editable_sources": ["top.sv", "top.sv"]},
            {"memory_mb": True},
            {"memory_mb": 255},
            {"memory_mb": 262145},
            {"frontend": {"kind": "arbitrary-shell"}},
        ):
            write_document(self.project, {**project, **fields})
            with self.subTest(fields=fields), self.assertRaises(ValueError):
                load_rtl_project(self.project)
        write_document(self.project, {**project, "editable_sources": ["top.sv"], "memory_mb": 8192})
        self.assertEqual(load_rtl_project(self.project)["memory_mb"], 8192)

    @skipUnless(
        (Path(__file__).resolve().parents[2] / "schemas/signoff/rtl-project-v1.schema.json").is_file(),
        "private RTL schema unavailable",
    )
    def test_private_schema_covers_source_scope_and_pinned_frontend(self):
        from jsonschema import Draft202012Validator

        schema = json.loads(
            (Path(__file__).resolve().parents[2] / "schemas/signoff/rtl-project-v1.schema.json").read_text()
        )
        Draft202012Validator.check_schema(schema)
        validate = Draft202012Validator(schema)
        project = json.loads(self.project.read_text())
        validate.validate(project)
        project.update(
            editable_sources=["top.sv"],
            memory_mb=8192,
            frontend={
                "kind": "sv2v",
                "executable": "tools/sv2v",
                "sha256": "a" * 64,
                "defines": ["SYNTHESIS", "VERILATOR"],
            },
        )
        validate.validate(project)
        for changed in (
            {"memory_mb": True},
            {"sources": ["../escape.sv"]},
            {"documents": ["docs//design.md"]},
            {"unknown": 1},
        ):
            with self.subTest(changed=changed):
                self.assertFalse(validate.is_valid({**project, **changed}))

    def test_model_does_not_receive_unselected_dependencies_but_compiler_does(self):
        project = json.loads(self.project.read_text())
        (self.root / "types.sv").write_text("// immutable dependency unavailable to the proposal\n")
        project.update(sources=["types.sv", "top.sv"], editable_sources=["top.sv"])
        write_document(self.project, project)
        client = Client([{**RTL_PROPOSAL, "edits": None}])
        with (
            patch(f"{BACKEND}.lower_rtl_sources", return_value=self.root / "logical.v") as lower,
            patch(f"{BACKEND}.measure_rtl", return_value={"analysis": analysis()}),
        ):
            result = run_rtl_optimization(self.config, self.project, max_iterations=1, model_client=client)
        self.assertEqual(result["stop_reason"], "agent_stopped")
        self.assertEqual(lower.call_args.args[1], ["types.sv", "top.sv"])
        context = json.loads(client.requests[0].user_prompt)
        self.assertEqual(set(context["sources"]), {"top.sv"})

    def test_cli_dispatch_and_failure_exit_code(self):
        with (
            patch("dv_platform.enterprise.cli._config", return_value=self.config),
            patch(f"{BACKEND}.run_rtl_optimization", return_value={"status": "no_improvement"}) as run,
        ):
            code, result = _main(["--json", "rtl-optimize", "--project", str(self.project), "--max-iterations", "1"])
        self.assertEqual(code, 1)
        self.assertEqual(result["data"]["status"], "no_improvement")
        self.assertEqual(run.call_args.kwargs["max_iterations"], 1)
