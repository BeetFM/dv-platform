import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch

from dv_platform.ai.model_client import ModelResponse
from dv_platform.core.config import default_config
from dv_platform.domain.models import AIConfig
from dv_platform.enterprise.physical_design import (
    _execute_case,
    _resolved_constraints_digest,
    run_physical_optimization,
)
from dv_platform.physical_design import file_digest
from dv_platform.product import CapabilityDeniedError, resolve_configured_product_plan
from tests.ai.test_physical_design import PROPOSAL, REPAIR, Client, analysis
from tests.domain.test_physical_design import native_metrics, project_fixture
from tests.enterprise.test_enterprise_cli import _main
from tests.support.entitlements import issue_test_entitlement

BACKEND = "dv_platform.enterprise.physical_design"


def candidate(wns=-0.01, tns=-0.1, area=650):
    measured = deepcopy(analysis())
    measured["metrics"].update(
        setup_wns_ns=wns, setup_tns_ns=tns, area_um2=area, repair_design_calls=1, repair_timing_calls=1
    )
    return measured


class PhysicalOptimizationTests(TestCase):
    def setUp(self):
        self.temporary = TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        self.project, self.manifest = project_fixture(self.root)
        self.config = replace(
            default_config(self.root),
            allow_network=True,
            ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            product=issue_test_entitlement(self.root, ("cli.enterprise", "adapter.enterprise")),
        )
        for name, value in (("_executable", "fixture-tool"), ("_version", "fixture-version")):
            patcher = patch(f"{BACKEND}.{name}", return_value=value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def run_cases(self, cases, *, config=None, iterations=1, replies=None):
        client = Client(
            replies
            if replies is not None
            else [{**PROPOSAL, "repair": {**REPAIR, "cap_margin_percent": 20 - index}} for index in range(iterations)]
        )
        with patch(f"{BACKEND}._execute_case", side_effect=cases) as execute:
            record = run_physical_optimization(
                config or self.config, self.project, use_ai=True, max_iterations=iterations, model_client=client
            )
        return record, client, execute

    def test_audited_model_proposal_is_executed_and_selected_without_claiming_signoff(self):
        record, client, execute = self.run_cases([analysis(), candidate()])
        self.assertEqual(record["selected"], "candidate-1")
        self.assertEqual(record["model_transport"], "injected_client")
        self.assertEqual(record["model_call_count"], 1)
        self.assertEqual(record["model_accepted_responses"], 1)
        self.assertEqual(len(client.requests), 1)
        self.assertEqual(execute.call_args.args[-1], REPAIR)
        self.assertFalse(record["signoff_approved"])
        self.assertEqual(record["logical_equivalence"], "not_checked")
        self.assertEqual((Path(record["output"]) / "run.json").stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / "constraints.sdc").read_text(), "fixture\n")

    def test_regressing_total_slack_is_rejected_despite_improved_worst_slack(self):
        record, _, _ = self.run_cases([analysis(), candidate(tns=-0.5)])
        self.assertEqual(record["selected"], "baseline")
        self.assertFalse(record["iterations"][0]["selected"])
        self.assertEqual(record["status"], "timing_open")
        self.assertEqual(record["iterations"][0]["evaluation"]["regressions"], ["setup_tns_ns"])

    def test_next_experiment_uses_rejected_result_and_stops_on_measured_closure(self):
        test = self

        class FeedbackClient:
            calls = 0

            def complete(self, request):
                context = json.loads(request.user_prompt)
                self.calls += 1
                repair = REPAIR
                if context["history"]:
                    previous = context["history"][-1]
                    test.assertFalse(previous["selected"])
                    test.assertEqual(previous["evaluation"]["regressions"], ["setup_tns_ns"])
                    test.assertEqual(context["analysis"]["metrics"]["setup_wns_ns"], -0.03)
                    repair = {**previous["repair"], "cap_margin_percent": 10}
                return ModelResponse(json.dumps({**PROPOSAL, "repair": repair}))

        closed = candidate(wns=0.01, tns=0)
        closed["metrics"]["cap_slack_percent"] = 10
        closed.update(timing_closed=True, failures=[])
        client = FeedbackClient()
        with patch(f"{BACKEND}._execute_case", side_effect=[analysis(), candidate(tns=-0.5), closed]) as execute:
            record = run_physical_optimization(self.config, self.project, use_ai=True, model_client=client)
        self.assertEqual(record["iteration_budget"], 3)
        self.assertEqual(client.calls, 2)
        self.assertEqual(execute.call_count, 3)
        self.assertEqual(execute.call_args.args[-1]["cap_margin_percent"], 10)
        self.assertEqual([step["selected"] for step in record["iterations"]], [False, True])
        self.assertEqual(record["selected"], "candidate-2")
        self.assertEqual(record["status"], record["stop_reason"])
        self.assertEqual(record["status"], "timing_closed")
        self.assertEqual(record["assessment"]["unmet_requirements"], [])
        self.assertFalse(record["signoff_approved"])

    def test_budget_exhaustion_keeps_best_result_and_remaining_requirements(self):
        record, client, _ = self.run_cases(
            [analysis(), candidate(wns=-0.02, tns=-0.2), candidate(wns=-0.015, tns=-0.15), candidate()], iterations=3
        )
        self.assertEqual(len(record["iterations"]), 3)
        self.assertEqual(record["stop_reason"], "iteration_budget_exhausted")
        self.assertEqual(record["status"], "timing_open")
        self.assertEqual(record["selected"], "candidate-3")
        self.assertEqual(
            record["assessment"]["unmet_requirements"], ["setup_wns_ns", "setup_tns_ns", "cap_slack_percent"]
        )
        last_context = json.loads(client.requests[-1].user_prompt)
        self.assertEqual(len(last_context["history"]), 2)
        self.assertEqual(last_context["requirements"]["metrics"]["area_um2"]["target"], 720)

    def test_agent_can_stop_with_an_explanation_without_claiming_closure(self):
        stop = {
            **PROPOSAL,
            "repair": None,
            "target_metrics": [],
            "hypothesis": "No untried supported repair is justified.",
        }
        record, _, execute = self.run_cases([analysis()], iterations=3, replies=[stop])
        self.assertEqual(record["stop_reason"], "agent_stopped")
        self.assertEqual(record["status"], "timing_open")
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(len(record["assessment"]["unmet_requirements"]), 3)

    def test_growth_limit_applies_to_original_baseline_across_iterations(self):
        record, _, _ = self.run_cases(
            [analysis(), candidate(wns=-0.02, area=710), candidate(wns=-0.01, area=800)], iterations=2
        )
        self.assertEqual(record["selected"], "candidate-1")
        self.assertEqual([step["selected"] for step in record["iterations"]], [True, False])

    def test_denied_network_records_zero_model_calls_and_runs_no_candidate(self):
        record, client, execute = self.run_cases(
            [analysis()], config=replace(self.config, allow_network=False), replies=[]
        )
        self.assertEqual(record["status"], "ai_unavailable")
        self.assertFalse(record["ai_invoked"])
        self.assertEqual(record["model_call_count"], 0)
        self.assertEqual(client.requests, [])
        self.assertEqual(execute.call_count, 1)
        self.assertEqual(record["iterations"][0]["fallback_reason"], "network_denied")

    def test_closed_baseline_does_not_call_model_or_approve_signoff(self):
        closed = analysis()
        closed.update(timing_closed=True, failures=[])
        closed["metrics"].update(setup_wns_ns=0.1, setup_tns_ns=0, cap_slack_percent=10)
        record, client, execute = self.run_cases([closed], replies=[])
        self.assertEqual(record["status"], "timing_closed")
        self.assertFalse(record["ai_invoked"])
        self.assertFalse(record["signoff_approved"])
        self.assertEqual(client.requests, [])
        self.assertEqual(execute.call_count, 1)

    def test_changed_source_is_detected_and_failure_evidence_is_persisted(self):
        def mutate(*args):
            (self.root / "constraints.sdc").write_text("changed\n")
            return analysis()

        with patch(f"{BACKEND}._execute_case", side_effect=mutate), self.assertRaisesRegex(ValueError, "input changed"):
            run_physical_optimization(self.config, self.project)
        record_path = next(self.config.work_dir.glob("physical-design/*/run.json"))
        record = json.loads(record_path.read_text())
        self.assertEqual(record["status"], "error")
        self.assertIn("finished_at", record)

    def test_explicit_invalid_entitlement_cannot_reuse_a_previous_active_plan(self):
        plan = resolve_configured_product_plan(self.config)
        invalid = replace(self.config, product=replace(self.config.product, entitlement_path=self.root / "missing"))
        with patch(f"{BACKEND}.active_product_plan", return_value=plan), self.assertRaises(CapabilityDeniedError):
            run_physical_optimization(invalid, self.project)

    def test_native_execution_obeys_the_actual_entitlement_concurrency_bound(self):
        from dv_platform.entitlement_leases import acquire_capability_lease

        plan = resolve_configured_product_plan(self.config)
        leases = [
            acquire_capability_lease(plan, self.config.work_dir, "cli.enterprise.physical-optimize")
            for _ in range(plan.concurrency_limit)
        ]
        try:
            with patch(f"{BACKEND}._execute_case") as execute, self.assertRaises(CapabilityDeniedError):
                run_physical_optimization(self.config, self.project)
            execute.assert_not_called()
        finally:
            for lease in leases:
                lease.release()
        self.assertEqual(list((self.config.work_dir / "entitlement/leases").glob("*.json")), [])

    def test_required_code_graph_is_used_and_failure_stops_model_and_candidate_calls(self):
        from dv_platform.ai.code_graph import CodeGraphResult
        from dv_platform.domain.models import ContextOptimizationConfig

        config = replace(self.config, context_optimization=ContextOptimizationConfig(code_graph_mode="required"))
        graph = CodeGraphResult("bounded advisory graph", None, 1, "available", provenance={"outcome": "available"})
        with patch(f"{BACKEND}.code_graph_context", return_value=graph):
            record, client, _ = self.run_cases([analysis(), candidate()], config=config)
        context = json.loads(client.requests[0].user_prompt)
        self.assertEqual(context["advisory_context"], "bounded advisory graph")
        self.assertEqual(record["code_graph"]["status"], "available")
        client = Client([])
        with (
            patch(f"{BACKEND}._execute_case", return_value=analysis()) as execute,
            patch(f"{BACKEND}.code_graph_context", side_effect=RuntimeError("required graph unavailable")),
        ):
            with self.assertRaisesRegex(ValueError, "required graph unavailable"):
                run_physical_optimization(config, self.project, use_ai=True, model_client=client)
            self.assertEqual(execute.call_count, 1)
        self.assertEqual(client.requests, [])

    def test_separate_sta_process_must_agree_before_analysis_is_accepted(self):
        work = self.root / "case"

        def execute(invocation, **kwargs):
            spef = invocation.cwd / self.manifest["parasitics"]
            spef.parent.mkdir()
            spef.write_text("fresh parasitics\n")
            return SimpleNamespace(passed=True)

        replay = {"setup_wns_ns": 0.1, "hold_wns_ns": 0.04, "setup_tns_ns": -0.24, "constraints_ok": 1}
        inputs = {name: file_digest(self.root / name) for name in self.manifest["inputs"]}
        with (
            patch(f"{BACKEND}.OpenROADRunner.execute", side_effect=execute),
            patch(f"{BACKEND}.read_physical_analysis", return_value=analysis()),
            patch(f"{BACKEND}._replay_sta", return_value=replay),
            self.assertRaisesRegex(ValueError, "OpenSTA disagrees"),
        ):
            _execute_case(
                self.config, work, self.root, self.manifest, inputs, {"openroad": "fake", "sta": "fake"}, None
            )

    def test_multicorner_repair_compares_sta_with_the_same_declared_scenario(self):
        project = deepcopy(self.manifest)
        project.update(
            schema_version=2,
            scenarios=[
                {"name": pvt, "pvt": pvt, "parasitics": project["parasitics"], "constraints": project["constraints"]}
                for pvt in ("tt_025C_1v80", "ss_100C_1v60", "ff_n40C_1v95")
            ],
        )
        replay = {"setup_wns_ns": 0.3, "hold_wns_ns": 0.04, "setup_tns_ns": 0, "constraints_ok": 1}

        def execute(invocation, **kwargs):
            work = invocation.cwd
            for name in (
                "pd-export.v",
                "pd-export.sdc",
                "pd-final.odb",
                "pd-final.def",
                "pd-timing.rpt",
                "pd-power.rpt",
                "pd-summary.json",
                "sta-driver.tcl",
                "sta-result.json",
                "openroad.stdout.log",
                "openroad.stderr.log",
                "sta.stdout.log",
                "sta.stderr.log",
                project["parasitics"],
            ):
                target = work / name
                target.parent.mkdir(exist_ok=True)
                target.write_text("test evidence\n")
            metrics = native_metrics()
            metrics["PD::view_count"] = 3
            (work / "pd-metrics.json").write_text(json.dumps(metrics))
            (work / "pd-power.json").write_text(json.dumps({"Total": {"total": 0.0024}}))
            return SimpleNamespace(passed=True)

        inputs = {name: file_digest(self.root / name) for name in self.manifest["inputs"]}
        for key in (None, "setup_wns_ns", "hold_wns_ns", "setup_tns_ns", "constraints_ok", "missing", "duplicate"):
            embedded = {name: value for name, value in replay.items() if name != "constraints_ok"}
            embedded["constraint_slack"] = 0
            if key in replay:
                field = "constraint_slack" if key == "constraints_ok" else key
                embedded[field] -= 1

            def augment(analysis, *args, report=embedded):
                analysis["scenarios"] = {"tt_025C_1v80": {"embedded_metrics": report}}

            with (
                self.subTest(key=key),
                patch(f"{BACKEND}.OpenROADRunner.execute", side_effect=execute),
                patch(f"{BACKEND}._replay_sta", return_value=replay),
                patch("dv_platform.enterprise.timing.export_logical_netlist", return_value=[]),
                patch("dv_platform.enterprise.timing.augment_analysis", side_effect=augment),
                patch("dv_platform.enterprise.timing.scenario_artifacts", return_value={}),
            ):
                work = self.root / ("multicorner-" + str(key))
                trial = deepcopy(project)
                if key == "missing":
                    trial["scenarios"][0]["parasitics"] = "alternate.spef"
                elif key == "duplicate":
                    trial["scenarios"].append(deepcopy(trial["scenarios"][0]))
                if key is None:
                    result = _execute_case(
                        self.config, work, self.root, trial, inputs, {"openroad": "fake", "sta": "fake"}, None
                    )
                    self.assertEqual(result["implementation_view_count"], 3)
                else:
                    reason = (
                        "requires one declared typical primary scenario"
                        if key in {"missing", "duplicate"}
                        else "OpenSTA disagrees with the primary scenario"
                    )
                    with self.assertRaisesRegex(ValueError, reason):
                        _execute_case(
                            self.config, work, self.root, trial, inputs, {"openroad": "fake", "sta": "fake"}, None
                        )
                    self.assertFalse((work / "analysis.json").exists())

    def test_constraint_fingerprint_ignores_export_timestamp_and_detects_exceptions(self):
        path = self.root / "export.sdc"
        path.write_text("# first export\ncreate_clock -period 0.485 [get_ports clk]\n")
        original = _resolved_constraints_digest(path)
        path.write_text("# later export\n\ncreate_clock -period 0.485 [get_ports clk]\n")
        self.assertEqual(_resolved_constraints_digest(path), original)
        path.write_text(path.read_text() + "set_false_path -to [all_outputs]\n")
        self.assertNotEqual(_resolved_constraints_digest(path), original)

    def test_cli_passes_ai_options_and_fails_when_timing_remains_open(self):
        for state, expected in (("timing_closed", 0), ("timing_open", 1), ("ai_unavailable", 1)):
            with (
                self.subTest(state=state),
                patch("dv_platform.enterprise.cli._config", return_value=self.config),
                patch(f"{BACKEND}.run_physical_optimization", return_value={"status": state}) as optimize,
            ):
                code, payload = _main(
                    ["--json", "physical-optimize", "--project", str(self.project), "--ai", "--max-iterations", "2"]
                )
                self.assertEqual(code, expected)
                self.assertEqual(payload["data"]["status"], state)
                optimize.assert_called_once_with(self.config, self.project, use_ai=True, max_iterations=2)

    def test_cli_defaults_to_three_experiments(self):
        from dv_platform.enterprise.cli import build_parser

        args = build_parser().parse_args(["physical-optimize", "--project", str(self.project), "--ai"])
        self.assertEqual(args.max_iterations, 3)
