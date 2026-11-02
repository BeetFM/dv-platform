import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.model_client import ModelResponse, ai_readiness
from dv_platform.ai.physical_design import propose_physical_repair
from dv_platform.core.config import default_config, validate_ai_config
from dv_platform.domain.models import AIConfig
from dv_platform.physical_design import (
    evaluate_physical_candidate,
    physical_improvement,
    physical_requirements,
    validate_repair,
)

REPAIR = {
    "cap_margin_percent": 20,
    "slew_margin_percent": 0,
    "setup_margin_ns": 0.03,
    "hold_margin_ns": 0,
    "allow_gate_cloning": True,
}
PROPOSAL = {
    "diagnosis": "Capacitance and setup slack fail on the measured path.",
    "evidence_ids": ["setup:0", "metric:cap_slack_percent"],
    "target_metrics": ["setup_wns_ns", "setup_tns_ns", "cap_slack_percent"],
    "hypothesis": "Repair capacitance with headroom and give setup repair a positive margin to reduce the path deficit.",
    "repair": REPAIR,
}


def analysis():
    return {
        "metrics": {
            "setup_wns_ns": -0.03,
            "hold_wns_ns": 0.04,
            "setup_tns_ns": -0.24,
            "cap_slack_percent": -6,
            "slew_slack_percent": 30,
            "fanout_slack_percent": 100,
            "area_um2": 600,
            "power_watts": 0.0024,
            "routed": 1,
            "constraints_ok": 1,
            "drc_violations": 0,
            "antenna_violations": 0,
        },
        "clocks": {"core": 0.485},
        "resolved_constraints_sha256": "unchanged",
        "paths": [
            {
                "evidence_id": "setup:0",
                "mode": "setup",
                "startpoint": "reg/Q",
                "endpoint": "resp[15]",
                "slack_ns": -0.03,
                "arrival_ns": 0.1,
                "required_arrival_ns": 0.07,
                "points": [{"pin": "reg/Q", "arrival_ns": 0.1}],
            }
        ],
        "failures": ["setup_wns_ns", "setup_tns_ns", "cap_slack_percent"],
        "timing_closed": False,
        "directory": "/private/path/which/must/not/reach/the/model",
    }


class Client:
    def __init__(self, replies):
        self.replies = iter(replies)
        self.requests = []

    def complete(self, request):
        self.requests.append(request)
        return ModelResponse(json.dumps(next(self.replies)), prompt_tokens=10, completion_tokens=20, total_tokens=30)


class PhysicalDesignAITests(TestCase):
    def test_measured_evidence_reaches_gateway_and_receipt_records_model_response(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            self.assertEqual(validate_ai_config(config.ai), ())
            self.assertEqual(ai_readiness(config)["stages"]["physical_design"], "active")
            reply = deepcopy(PROPOSAL)
            client = Client([reply])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
            )
            self.assertEqual(proposal, reply)
            self.assertEqual(result.status, "accepted")
            self.assertEqual(len(client.requests), 1)
            context = client.requests[0].user_prompt
            self.assertIn("resp[15]", context)
            self.assertNotIn("/private/path", context)
            observations = json.loads(context)
            self.assertEqual(observations["requirements"]["metrics"]["setup_wns_ns"]["target"], 0)
            self.assertEqual(observations["assessment"]["checks"]["setup_wns_ns"]["gap"], 0.03)
            self.assertEqual(observations["requirements"]["metrics"]["area_um2"]["target"], 720)
            receipt = json.loads(result.run_record_path.read_text())
            self.assertEqual(receipt["purpose"], "physical_design")
            self.assertEqual(receipt["token_usage"]["total"], 30)
            self.assertIsNotNone(receipt["proposal_hash"])

    def test_invented_evidence_and_script_output_trigger_bounded_repair(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            valid = deepcopy(PROPOSAL)
            forged = {**valid, "evidence_ids": ["invented:path"]}
            executable = {**valid, "repair": {**REPAIR, "tcl": "set_false_path -from [all_inputs]"}}
            client = Client([forged, executable, valid])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
            )
            self.assertEqual(proposal, valid)
            self.assertEqual(result.attempts, 3)
            self.assertEqual(len(client.requests), 3)

    def test_network_denial_never_calls_model_or_invents_a_repair(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            client = Client([])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
            )
            self.assertIsNone(proposal)
            self.assertEqual(result.fallback_reason, "network_denied")
            self.assertEqual(client.requests, [])

    def test_repair_parameters_reject_injection_nonfinite_numbers_and_spec_changes(self):
        for invalid in (
            {**REPAIR, "setup_margin_ns": "0;exec bad"},
            {**REPAIR, "cap_margin_percent": True},
            {**REPAIR, "cap_margin_percent": 31},
            {**REPAIR, "cap_margin_percent": 10**400},
            {**REPAIR, "setup_margin_ns": float("nan")},
            {**REPAIR, "clock_period": 1},
            {**REPAIR, "allow_gate_cloning": "true"},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_repair(invalid)

    def test_restricted_data_without_approved_routing_never_reaches_model(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",), data_class="restricted"),
            )
            client = Client([])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
            )
            self.assertIsNone(proposal)
            self.assertEqual(result.fallback_reason, "restricted_data_requires_policy")
            self.assertEqual(client.requests, [])

    def test_invalid_sdk_configuration_cannot_expand_model_retry_budget(self):
        with TemporaryDirectory() as directory:
            config = replace(default_config(Path(directory)), ai=AIConfig(max_repair_attempts=100))
            client = Client([])
            with self.assertRaisesRegex(ValueError, "max_repair_attempts"):
                propose_physical_repair(
                    LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
                )
            self.assertEqual(client.requests, [])

    def test_selection_rejects_regressions_and_never_accepts_a_relaxed_clock(self):
        baseline = analysis()
        candidate = deepcopy(baseline)
        candidate["metrics"].update({"setup_wns_ns": -0.01, "setup_tns_ns": -0.1, "cap_slack_percent": -2})
        self.assertTrue(physical_improvement(baseline, candidate))
        for name, value in (
            ("hold_wns_ns", -0.01),
            ("cap_slack_percent", -8),
            ("drc_violations", 1),
            ("area_um2", 800),
            ("power_watts", 0.003),
            ("setup_tns_ns", -0.5),
        ):
            changed = deepcopy(candidate)
            changed["metrics"][name] = value
            self.assertFalse(physical_improvement(baseline, changed), name)
        candidate["clocks"]["core"] = 1
        with self.assertRaisesRegex(ValueError, "timing specification"):
            physical_improvement(baseline, candidate)
        candidate["clocks"] = baseline["clocks"]
        candidate["resolved_constraints_sha256"] = "changed_exception"
        with self.assertRaisesRegex(ValueError, "timing specification"):
            physical_improvement(baseline, candidate)

    def test_selection_recognizes_hold_electrical_and_total_slack_progress(self):
        for name, before, after in (
            ("hold_wns_ns", -0.04, -0.01),
            ("cap_slack_percent", -6, -2),
            ("setup_tns_ns", -0.24, -0.1),
        ):
            baseline = analysis()
            baseline["metrics"].update(setup_wns_ns=0.1, setup_tns_ns=0, cap_slack_percent=10)
            baseline["metrics"][name] = before
            candidate = deepcopy(baseline)
            candidate["metrics"][name] = after
            with self.subTest(metric=name):
                self.assertTrue(physical_improvement(baseline, candidate))

    def test_rejected_experiment_feeds_next_decision_and_duplicate_recipe_is_not_reexecuted(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            baseline = analysis()
            rejected = deepcopy(baseline)
            rejected["metrics"]["setup_tns_ns"] = -0.5
            history = [
                {
                    "iteration": 1,
                    "proposal": PROPOSAL,
                    "selected": False,
                    "candidate": rejected,
                    "evaluation": evaluate_physical_candidate(baseline, baseline, rejected),
                }
            ]
            revised = {
                **PROPOSAL,
                "repair": {**REPAIR, "cap_margin_percent": 10},
                "hypothesis": "Reduce over-repair because the previous candidate worsened total negative slack.",
            }
            client = Client([PROPOSAL, revised])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), baseline, history, physical_requirements(baseline)
            )
            self.assertEqual(proposal, revised)
            self.assertEqual(result.attempts, 2)
            context = json.loads(client.requests[0].user_prompt)
            self.assertEqual(context["history"][0]["evaluation"]["regressions"], ["setup_tns_ns"])
            self.assertEqual(context["history"][0]["hypothesis"], PROPOSAL["hypothesis"])
            self.assertEqual(context["history"][0]["paths"][0]["evidence_id"], "iteration:1:setup:0")
            self.assertIn("iteration:1:setup:0", context["evidence_ids"])
            self.assertIn("already measured", client.requests[1].user_prompt)

    def test_repair_cannot_claim_to_target_an_already_satisfied_requirement(self):
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            client = Client([{**PROPOSAL, "target_metrics": ["hold_wns_ns"]}, PROPOSAL])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), analysis(), [], physical_requirements(analysis())
            )
            self.assertEqual(proposal, PROPOSAL)
            self.assertEqual(result.attempts, 2)

    def test_nine_view_context_is_lossless_for_requirements_and_fits_the_existing_budget(self):
        from dv_platform.enterprise.timing import TIMING_FIELDS
        from dv_platform.signoff import PVT_CORNERS, RC_CORNERS

        measured = analysis()
        measured["production_limits"] = {
            "area_max_um2": None,
            "power_max_watts": None,
            "setup_margin_ns": 0,
            "hold_margin_ns": 0,
        }
        measured["scenarios"] = {}
        for pvt in PVT_CORNERS:
            for rc in RC_CORNERS:
                name = f"functional_{pvt}_{rc}"
                metrics = {field: measured["metrics"].get(field, 0) for field in TIMING_FIELDS}
                metrics["power_watts"] = 0.0024
                measured["scenarios"][name] = {"metrics": metrics, "clocks": {"clk": 100}}
                measured["metrics"].update(
                    {f"scenario:{name}:{key}": value for key, value in metrics.items() if key in TIMING_FIELDS}
                )
        requirements = physical_requirements(measured)
        history = [
            {
                "iteration": i,
                "proposal": {**PROPOSAL, "repair": {**REPAIR, "cap_margin_percent": i}},
                "selected": False,
                "candidate": measured,
                "evaluation": evaluate_physical_candidate(measured, measured, measured),
            }
            for i in (1, 2)
        ]
        with TemporaryDirectory() as directory:
            config = replace(
                default_config(Path(directory)),
                allow_network=True,
                ai=AIConfig(model="fixture/physical", allowed_stages=("physical_design",)),
            )
            client = Client([PROPOSAL])
            proposal, result = propose_physical_repair(
                LiteLLMGateway(config, client), measured, history, requirements, advisory_context="x" * 4000
            )
        self.assertEqual(result.status, "accepted")
        self.assertEqual(proposal, PROPOSAL)
        context = client.requests[0].user_prompt
        self.assertLessEqual(len(context), config.ai.max_context_chars)
        data = json.loads(context)
        gates = data["requirements"]["metrics"].copy()
        factored = data["requirements"]["scenario_metrics"]
        for name in factored["scenarios"]:
            gates.update({f"scenario:{name}:{field}": gate for field, gate in factored["metrics"].items()})
        self.assertEqual(gates, requirements["metrics"])
        self.assertEqual(data["analysis"]["scenarios"], measured["scenarios"])
        self.assertEqual(len(data["history"]), 2)
        self.assertEqual(data["history"][1]["scenarios"], measured["scenarios"])
