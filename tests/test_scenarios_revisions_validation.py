import ast
import io
import json
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.agent.contracts import AgentProposal, FeedbackEvent
from dv_platform.agent.protocols import RegisterField, RegisterModel, apb4_model, axi4_lite_model
from dv_platform.analysis.ai_feedback import _validate_feedback_response, propose_feedback_operations
from dv_platform.analysis.ai_gateway import LiteLLMGateway
from dv_platform.analysis.ai_planning import AIPlanningError, ModelResponse, validate_proposal
from dv_platform.analysis.ai_scenarios import synthesize_scenario_selections
from dv_platform.analysis.plan_store import write_plan_outputs
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.revisions import create_feedback_revision, read_revision_plan
from dv_platform.analysis.scenarios import build_deterministic_scenarios, validate_scenario
from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import (
    AIConfig,
    EvidenceKind,
    EvidenceRef,
    RTLClock,
    RTLModule,
    RTLPort,
    RTLReset,
    ScenarioCompletion,
    ScenarioCoverageGoal,
    ScenarioOracle,
    ScenarioStimulus,
    VerificationCheck,
    VerificationPlan,
    VerificationScenario,
    VerificationTarget,
)
from dv_platform.core.validation import validation_result_from_coverage, validation_result_from_json
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.formal import FormalGenerator
from dv_platform.generators.systemverilog import SystemVerilogGenerator


class SequenceClient:
    def __init__(self, *responses: str | ModelResponse | Exception) -> None:
        self.responses = list(responses)

    def complete(self, _request):
        value = self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        if isinstance(value, ModelResponse):
            return value
        return ModelResponse(value)


class ScenarioRevisionValidationTests(unittest.TestCase):
    def test_planner_never_marks_scaffolded_protocol_checks_executable(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vbus.xml", "module:bus"),)
        apb_names = ("psel", "penable", "pwrite", "paddr", "pwdata", "prdata", "pready", "pstrb", "pslverr")
        axi_names = (
            "awvalid",
            "awready",
            "wvalid",
            "wready",
            "bvalid",
            "bready",
            "arvalid",
            "arready",
            "rvalid",
            "rready",
        )
        apb_directions = {name: "output" if name in {"prdata", "pready", "pslverr"} else "input" for name in apb_names}
        qualified_apb = replace(
            apb4_model(tuple((name, name) for name in apb_names), evidence),
            signal_directions=tuple(apb_directions.items()),
            clock_domain="pclk",
            reset_domain="presetn",
        )
        qualified_register = RegisterModel(
            "CONTROL",
            0,
            32,
            (RegisterField("ENABLE", 0, 0, "0", "rw", evidence_refs=evidence),),
            invalid_address_behavior="pslverr",
            byte_enable_behavior="pstrb",
            source="configuration",
            evidence_refs=evidence,
        )
        apb = create_initial_plan(
            RTLModule(
                "apb",
                port_details=tuple(RTLPort(name, direction) for name, direction in apb_directions.items())
                + (RTLPort("pclk", "input"), RTLPort("presetn", "input")),
                clock_details=(RTLClock("pclk", "input"),),
                reset_details=(RTLReset("presetn", "input", active_low=True),),
                protocol_models=(qualified_apb,),
                register_models=(qualified_register,),
                ast_refs=evidence,
            ),
            (VerificationTarget.COCOTB,),
        )
        axi = create_initial_plan(
            RTLModule(
                "axi",
                protocol_models=(axi4_lite_model(tuple((name, name) for name in axi_names), evidence),),
                ast_refs=evidence,
            ),
            (VerificationTarget.COCOTB,),
        )

        self.assertTrue(any(check.executable for check in apb.check_details if check.category == "protocol"))
        self.assertFalse(any(check.executable for check in axi.check_details if check.category == "protocol"))

    def test_complete_apb4_facts_create_executable_scenarios(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vapb.xml", "module:apb"),)
        directions = {
            "psel": "input",
            "penable": "input",
            "pwrite": "input",
            "paddr": "input",
            "pwdata": "input",
            "pstrb": "input",
            "prdata": "output",
            "pready": "output",
            "pslverr": "output",
        }
        model = replace(
            apb4_model(tuple((name, name) for name in directions), evidence),
            signal_directions=tuple(directions.items()),
            clock_domain="pclk",
            reset_domain="presetn",
        )
        check = VerificationCheck("apb:check", "Verify APB4 backpressure.", "protocol", True, evidence)
        plan = VerificationPlan(
            "apb",
            (VerificationTarget.COCOTB, VerificationTarget.SYSTEMVERILOG, VerificationTarget.FORMAL),
            ports=tuple(RTLPort(name, direction, width=1) for name, direction in directions.items())
            + (RTLPort("pclk", "input", width=1), RTLPort("presetn", "input", width=1)),
            protocol_models=(model,),
            resets=(RTLReset("presetn", "input", active_low=True),),
            register_models=(
                RegisterModel(
                    "CONTROL",
                    0,
                    32,
                    (RegisterField("enable", 0, 0, "0", "rw"),),
                    invalid_address_behavior="pslverr",
                    byte_enable_behavior="pstrb",
                    source="configuration",
                    evidence_refs=evidence,
                ),
            ),
            check_details=(check,),
        )

        scenarios = build_deterministic_scenarios(plan)

        self.assertEqual({scenario.kind for scenario in scenarios}, {"apb4_transfer", "apb4_register_access"})
        self.assertTrue(all(scenario.executable for scenario in scenarios))
        self.assertTrue(all(not validate_scenario(plan, scenario) for scenario in scenarios))
        planned = replace(plan, scenarios=scenarios)
        cocotb_artifact = CocotbGenerator().generate(planned)[0]
        generated = cocotb_artifact.content
        ast.parse(generated)
        self.assertIn("class APB4Driver", generated)
        self.assertIn("class APB4Monitor", generated)
        self.assertIn("APB4 register scoreboard mismatch", generated)
        self.assertTrue(any(check.check_id in trace.check_ids for trace in cocotb_artifact.traceability))
        self.assertTrue(
            any(
                check.check_id in trace.check_ids
                for artifact in FormalGenerator().generate(planned)
                for trace in artifact.traceability
            )
        )
        systemverilog = SystemVerilogGenerator().generate(planned)[0].content
        self.assertIn("assert property (@(posedge pclk) (psel && !penable)", systemverilog)
        self.assertIn("$stable({paddr, pwrite, pwdata, pstrb})", systemverilog)

    def test_additive_revision_changes_hash_and_loads_snapshot(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = EvidenceRef(EvidenceKind.TOOL_LOG, "event", "run:one")
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,))
            proposal = AgentProposal(
                "proposal",
                "task",
                "add_check",
                "Exercise the error response.",
                (evidence,),
                {
                    "operation": "add_check",
                    "check_id": "top:check:error",
                    "statement": "Exercise the error response.",
                    "category": "protocol",
                },
            )

            revision = create_feedback_revision(root, plan, (), proposals=(proposal,), evidence_ids={"event"})
            snapshot = read_revision_plan(root, revision.revision_id)

            self.assertNotEqual(revision.input_plan_hash, revision.resulting_plan_hash)
            self.assertEqual(len(revision.accepted_operations), 1)
            self.assertIsNotNone(snapshot)
            assert snapshot is not None
            self.assertEqual(snapshot.check_details[0].check_id, "top:check:error")
            self.assertFalse(snapshot.check_details[0].executable)

    def test_zero_executed_checks_is_unexecuted_even_with_zero_return_code(self) -> None:
        result = validation_result_from_coverage("top", VerificationTarget.VERILOG, "passed", 0, [])

        self.assertEqual(result.status, "unexecuted")
        self.assertEqual(validation_result_from_json(result.to_json()), result)

    def test_validation_contract_normalizes_failure_and_rejects_bad_documents(self) -> None:
        result = validation_result_from_coverage(
            "top",
            VerificationTarget.COCOTB,
            "failed",
            1,
            [{"check_id": "c1", "status": "failed", "generated_symbol": "test_c1"}],
        )
        self.assertEqual(result.status, "failed")
        self.assertEqual(result.checks[0].outcome, "fail")
        for payload in (
            {**result.to_json(), "schema_version": 99},
            {**result.to_json(), "checks": "bad"},
            {**result.to_json(), "checks": [{}]},
            {**result.to_json(), "checks": [{"check_id": "c", "outcome": "invented"}]},
        ):
            with self.subTest(payload=payload), self.assertRaises(ValueError):
                validation_result_from_json(payload)

    def test_scenario_validator_reports_unknown_links_signals_and_mappings(self) -> None:
        plan = VerificationPlan("top", (VerificationTarget.COCOTB,), ports=(RTLPort("known", "input"),))
        scenario = VerificationScenario(
            "scenario",
            "invented",
            (ScenarioStimulus("drive", "unknown", "1"),),
            ScenarioOracle("equals", "unknown", "1"),
            ScenarioCompletion("signal", "unknown", "1", 0),
            (),
            (VerificationTarget.COCOTB,),
            requirement_ids=("missing-requirement",),
            check_ids=("missing-check",),
        )
        diagnostics = validate_scenario(plan, scenario)
        self.assertGreaterEqual(len(diagnostics), 7)

    def test_axi_and_reset_scenarios_are_typed_but_fail_closed_without_full_evidence(self) -> None:
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vtop.xml", "module:top"),)
        names = ("awvalid", "awready", "wvalid", "wready", "bvalid", "bready", "arvalid", "arready", "rvalid", "rready")
        axi = axi4_lite_model(tuple((name, name) for name in names), evidence)
        checks = (
            VerificationCheck("protocol", "Verify backpressure.", "protocol", True, evidence),
            VerificationCheck("reset", "Verify reset.", "reset", True, evidence),
        )
        plan = VerificationPlan(
            "top",
            (VerificationTarget.COCOTB,),
            ports=tuple(RTLPort(name, "input") for name in names) + (RTLPort("rst_n", "input"),),
            resets=(RTLReset("rst_n", "input", active_low=True),),
            protocol_models=(axi,),
            check_details=checks,
            claims=(),
        )
        scenarios = build_deterministic_scenarios(plan)
        self.assertEqual({item.kind for item in scenarios}, {"axi4_lite_single_outstanding", "reset_sequence"})
        axi_scenario = next(item for item in scenarios if item.kind.startswith("axi4"))
        self.assertFalse(axi_scenario.executable)
        self.assertEqual(axi_scenario.target_states[0].state, "scaffold")
        self.assertIn("scoreboard", axi_scenario.target_states[0].reason or "")
        self.assertFalse(next(item for item in scenarios if item.kind == "reset_sequence").executable)

    def test_gateway_fallback_repair_and_feedback_proposal(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = default_config(root)
            disabled = LiteLLMGateway(replace(base, ai=AIConfig(model="test/model")))
            denied = disabled.execute(
                stage="planning", system_prompt="s", user_prompt="u", response_schema={}, context="c"
            )
            self.assertEqual(denied.fallback_reason, "network_denied")

            disallowed = LiteLLMGateway(
                replace(base, ai=AIConfig(model="test/model", allowed_stages=("planning",)))
            ).execute(
                stage="feedback_analysis",
                system_prompt="s",
                user_prompt="u",
                response_schema={},
                context="c",
            )
            self.assertEqual(disallowed.fallback_reason, "stage_not_allowed")

            missing_model = LiteLLMGateway(replace(base, allow_network=True)).execute(
                stage="planning", system_prompt="s", user_prompt="u", response_schema={}, context="c"
            )
            self.assertEqual(missing_model.fallback_reason, "model_not_configured")
            credential_config = replace(
                base,
                allow_network=True,
                ai=AIConfig(model="test/model", api_key_env="MISSING_GATEWAY_TEST_KEY"),
            )
            with patch.dict("os.environ", {}, clear=True):
                credential = LiteLLMGateway(credential_config).execute(
                    stage="planning", system_prompt="s", user_prompt="u", response_schema={}, context="c"
                )
            self.assertEqual(credential.fallback_reason, "credential_missing")

            config = replace(base, allow_network=True, ai=AIConfig(model="test/model", max_repair_attempts=1))
            repaired = LiteLLMGateway(config, SequenceClient("bad", '{"ok": true}')).execute(
                stage="planning",
                system_prompt="s",
                user_prompt="u",
                response_schema={},
                context="c",
                validate=lambda raw: json.loads(raw),
            )
            self.assertEqual(repaired.status, "accepted")
            self.assertEqual(repaired.attempts, 2)
            failed = LiteLLMGateway(
                config,
                SequenceClient(AIPlanningError("timeout", "timed out")),
            ).execute(stage="planning", system_prompt="s", user_prompt="u", response_schema={}, context="c")
            self.assertEqual(failed.fallback_reason, "timeout")
            exhausted = LiteLLMGateway(config, SequenceClient("bad", "still bad")).execute(
                stage="planning",
                system_prompt="s",
                user_prompt="u",
                response_schema={},
                context="c",
                validate=lambda raw: json.loads(raw),
            )
            self.assertEqual(exhausted.fallback_reason, "repair_attempts_exhausted")
            invalid_then_valid = LiteLLMGateway(
                config,
                SequenceClient(AIPlanningError("invalid_response", "bad schema"), '{"ok": true}'),
            ).execute(stage="planning", system_prompt="s", user_prompt="u", response_schema={}, context="c")
            self.assertEqual(invalid_then_valid.status, "accepted")

            feedback_json = json.dumps(
                {
                    "proposals": [
                        {
                            "proposal_id": "p1",
                            "operation": "add_check",
                            "statement": "Add an error check.",
                            "check_id": "top:check:error",
                            "scenario_id": None,
                            "goal_id": None,
                            "category": "protocol",
                            "kind": None,
                            "evidence_ids": ["e1"],
                        }
                    ]
                }
            )
            proposals, evidence_ids, result = propose_feedback_operations(
                LiteLLMGateway(config, SequenceClient(feedback_json)),
                VerificationPlan("top", (VerificationTarget.COCOTB,)),
                (FeedbackEvent("e1", "run", VerificationTarget.COCOTB, "top", "fail", check_id="c1"),),
            )
            self.assertEqual(result.status, "accepted")
            self.assertEqual(evidence_ids, {"e1"})
            self.assertEqual(proposals[0].payload["operation"], "add_check")

            invalid_feedback = (
                "[]",
                '{"proposals":[{}]}',
                json.dumps({"proposals": [{**json.loads(feedback_json)["proposals"][0], "evidence_ids": ["bad"]}]}),
                json.dumps({"proposals": [{**json.loads(feedback_json)["proposals"][0], "check_id": None}]}),
                json.dumps(
                    {
                        "proposals": [
                            {
                                **json.loads(feedback_json)["proposals"][0],
                                "operation": "add_coverage_goal",
                                "scenario_id": "missing",
                                "goal_id": "goal",
                            }
                        ]
                    }
                ),
            )
            for raw in invalid_feedback:
                with self.subTest(raw=raw), self.assertRaises(ValueError):
                    _validate_feedback_response(raw, {"e1"}, VerificationPlan("top", ()))

    def test_scenario_synthesis_selects_only_templates_and_records_common_audit_fields(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            scenario = VerificationScenario(
                "scenario-1",
                "reset_sequence",
                (ScenarioStimulus("hold", parameters=(("cycles", "2"),)),),
                ScenarioOracle("equals", "rst_n", "0"),
                ScenarioCompletion("cycles", timeout_cycles=4),
                (),
                (VerificationTarget.COCOTB,),
            )
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,), scenarios=(scenario,))
            config = replace(
                default_config(root),
                allow_network=True,
                ai=AIConfig(
                    model="test/model",
                    api_base="https://user:secret@example.test/v1?token=hidden",
                    allowed_stages=("scenario_synthesis",),
                    max_repair_attempts=1,
                ),
            )
            response = ModelResponse(
                json.dumps({"selections": [{"scenario_id": "scenario-1", "parameters": {"0:hold:cycles": "2"}}]}),
                prompt_tokens=7,
                completion_tokens=5,
                total_tokens=12,
                cost=0.01,
                retry_count=1,
            )

            selections, result = synthesize_scenario_selections(
                LiteLLMGateway(config, SequenceClient("not-json", response)), plan
            )

            self.assertEqual(result.status, "accepted")
            self.assertEqual(result.attempts, 2)
            self.assertEqual(selections[0].scenario_id, "scenario-1")
            self.assertEqual(selections[0].parameters, (("0:hold:cycles", "2"),))
            assert result.run_record_path is not None
            audit = json.loads(result.run_record_path.read_text(encoding="utf-8"))
            self.assertEqual(audit["purpose"], "scenario_synthesis")
            self.assertEqual(audit["endpoint"], "https://example.test/v1")
            self.assertEqual(audit["token_usage"]["total"], 12)
            self.assertEqual(audit["cost"], 0.01)
            self.assertEqual(audit["provider_retry_count"], 1)
            self.assertEqual(result.run_record_path.stat().st_mode & 0o777, 0o600)

            invalid = json.dumps(
                {
                    "selections": [
                        {"scenario_id": "scenario-1", "parameters": {}},
                        {"scenario_id": "invented", "parameters": {}},
                    ]
                }
            )
            empty, fallback = synthesize_scenario_selections(
                LiteLLMGateway(config, SequenceClient(invalid, invalid)), plan
            )
            self.assertEqual(empty, ())
            self.assertEqual(fallback.fallback_reason, "repair_attempts_exhausted")

    def test_feedback_cli_routes_both_ai_purposes_through_deterministic_fallback(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            check = VerificationCheck("check-1", "Check reset.")
            scenario = VerificationScenario(
                "scenario-1",
                "reset_sequence",
                (ScenarioStimulus("hold", parameters=(("cycles", "2"),)),),
                ScenarioOracle("equals", "rst_n", "0"),
                ScenarioCompletion("cycles", timeout_cycles=4),
                (),
                (VerificationTarget.COCOTB,),
                check_ids=(check.check_id,),
            )
            plan = VerificationPlan(
                "top",
                (VerificationTarget.COCOTB,),
                check_details=(check,),
                scenarios=(scenario,),
            )
            config = replace(
                default_config(root),
                ai=AIConfig(
                    model="test/model",
                    allowed_stages=("feedback_analysis", "scenario_synthesis"),
                ),
            )
            write_config(config, root / "dv-platform.toml")
            write_plan_outputs(config, (plan,))
            output = io.StringIO()

            with redirect_stdout(output):
                exit_code = main(
                    [
                        "--repo-root",
                        str(root),
                        "--json",
                        "feedback",
                        "--module",
                        "top",
                        "--target",
                        "cocotb",
                        "--ai",
                        "--dry-run",
                    ]
                )

            self.assertEqual(exit_code, 0, output.getvalue())
            ai = json.loads(output.getvalue())["data"]["ai"]
            self.assertEqual([item["purpose"] for item in ai], ["feedback_analysis", "scenario_synthesis"])
            self.assertTrue(all(item["fallback_reason"] == "network_denied" for item in ai))
            self.assertTrue(all(Path(item["run_record"]).is_file() for item in ai))

    def test_planning_proposal_v2_accepts_only_evidence_linked_scenario_intent(self) -> None:
        proposal = {
            "schema_version": 2,
            "module": "top",
            "requirements": [
                {
                    "proposal_id": "r1",
                    "statement": "Reset is observable.",
                    "signals": ["rst_n"],
                    "condition": None,
                    "expected_value": "0",
                    "evidence_ids": ["E1"],
                }
            ],
            "checks": [
                {
                    "proposal_id": "c1",
                    "statement": "Exercise reset.",
                    "requirement_ids": ["r1"],
                    "evidence_ids": ["E1"],
                }
            ],
            "scenarios": [
                {
                    "proposal_id": "s1",
                    "kind": "reset_sequence",
                    "requirement_ids": ["r1"],
                    "check_ids": ["c1"],
                    "evidence_ids": ["E1"],
                    "parameters": {"cycles": 2},
                }
            ],
            "assumptions": [],
            "open_questions": [],
        }
        parsed = validate_proposal(proposal, module="top", evidence_ids={"E1"}, known_signals={"rst_n"})
        self.assertEqual(parsed.scenarios[0].kind, "reset_sequence")
        invented = json.loads(json.dumps(proposal))
        invented["scenarios"][0]["check_ids"] = ["invented"]
        with self.assertRaises(AIPlanningError):
            validate_proposal(invented, module="top", evidence_ids={"E1"}, known_signals={"rst_n"})

    def test_revision_adds_coverage_goal_and_rejects_out_of_context_evidence(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            ref = EvidenceRef(EvidenceKind.TOOL_LOG, "e1", "run:one")
            scenario = VerificationScenario(
                "s1",
                "reset_sequence",
                (ScenarioStimulus("hold_cycles"),),
                ScenarioOracle("reset_observed"),
                ScenarioCompletion("cycles"),
                (ScenarioCoverageGoal("existing", "reset"),),
                (VerificationTarget.COCOTB,),
                evidence_refs=(ref,),
            )
            plan = VerificationPlan("top", (VerificationTarget.COCOTB,), scenarios=(scenario,))
            accepted = AgentProposal(
                "p1",
                "task",
                "coverage",
                "goal",
                (ref,),
                {"operation": "add_coverage_goal", "scenario_id": "s1", "goal_id": "new", "kind": "reset"},
            )
            rejected = AgentProposal(
                "p2", "task", "coverage", "bad", (EvidenceRef(EvidenceKind.TOOL_LOG, "bad", "bad"),)
            )
            revision = create_feedback_revision(root, plan, (), proposals=(accepted, rejected), evidence_ids={"e1"})
            snapshot = read_revision_plan(root, revision.revision_id)
            assert snapshot is not None
            self.assertEqual([goal.goal_id for goal in snapshot.scenarios[0].coverage_goals], ["existing", "new"])
            self.assertEqual(revision.rejected_proposal_ids, ("p2",))

            duplicate = AgentProposal(
                "p3",
                "task",
                "check",
                "duplicate",
                (ref,),
                {"operation": "add_check", "check_id": "existing"},
            )
            duplicate_plan = VerificationPlan("other", (), check_details=(VerificationCheck("existing", "existing"),))
            no_op = create_feedback_revision(
                root / "other", duplicate_plan, (), proposals=(duplicate,), evidence_ids={"e1"}
            )
            self.assertEqual(no_op.input_plan_hash, no_op.resulting_plan_hash)
            self.assertIsNone(read_revision_plan(root / "missing", "none"))

    def test_feedback_cli_reads_normalized_run_results_and_ai_falls_back(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = default_config(root)
            ref = EvidenceRef(EvidenceKind.TOOL_LOG, "run", "run:summary")
            check = VerificationCheck("top:check:one", "Check one.", "general", False, (ref,))
            write_plan_outputs(config, (VerificationPlan("top", (VerificationTarget.COCOTB,), check_details=(check,)),))
            summary = config.work_dir / "runs" / "simulation" / "cocotb" / "top" / "summary.json"
            summary.parent.mkdir(parents=True)
            summary.write_text(
                json.dumps(
                    {
                        "module": "top",
                        "validation_result": {"checks": [{"check_id": "top:check:one", "outcome": "fail"}]},
                    }
                ),
                encoding="utf-8",
            )
            return_code = main(
                [
                    "--repo-root",
                    str(root),
                    "--work-dir",
                    str(config.work_dir),
                    "feedback",
                    "--module",
                    "top",
                    "--from-runs",
                    "--ai",
                ]
            )
            self.assertEqual(return_code, 0)
            self.assertTrue((config.work_dir / "plans" / "revisions.sqlite").is_file())


if __name__ == "__main__":
    unittest.main()
