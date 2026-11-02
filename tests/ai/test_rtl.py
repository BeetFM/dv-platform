"""RTL proposals must cite design intent and stay inside the declared source surface."""

import json
from copy import deepcopy
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.ai.gateway import LiteLLMGateway
from dv_platform.ai.rtl import propose_rtl_edit
from dv_platform.core.config import default_config
from dv_platform.domain.models import AIConfig
from dv_platform.physical_design import assess_physical_requirements, physical_requirements
from tests.ai.test_physical_design import Client, analysis

RTL_PROPOSAL = {
    "diagnosis": "The output logic duplicates its input.",
    "hypothesis": "Remove the duplicate term while preserving the documented truth table.",
    "evidence_ids": ["source:top.sv", "document:design.md", "metric:area_um2"],
    "edits": [{"path": "top.sv", "before": "a & a", "after": "a"}],
}


class RTLProposalTests(TestCase):
    def run_proposals(self, replies, *, history=None, network=True, stages=("rtl_optimization",)):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        config = replace(
            default_config(Path(temporary.name)),
            allow_network=network,
            ai=AIConfig(model="fixture/rtl", allowed_stages=stages),
        )
        client = Client(replies)
        proposal, result = propose_rtl_edit(
            LiteLLMGateway(config, client),
            {"top.sv": "assign y = a & a;"},
            {"design.md": "y equals a"},
            analysis(),
            physical_requirements(analysis()),
            history or [],
            "area_um2",
        )
        return proposal, result, client

    def test_documents_sources_and_immutable_constraints_reach_model(self):
        proposal, result, client = self.run_proposals([RTL_PROPOSAL])
        self.assertEqual(proposal, RTL_PROPOSAL)
        self.assertEqual(result.status, "accepted")
        context = json.loads(client.requests[0].user_prompt)
        self.assertEqual(context["documents"], {"design.md": "y equals a"})
        self.assertEqual(context["requirements"]["clocks"], {"core": 0.485})
        self.assertNotIn("/private/path", client.requests[0].user_prompt)
        self.assertEqual(json.loads(result.run_record_path.read_text())["purpose"], "rtl_optimization")

    def test_forged_evidence_and_document_edits_are_repaired(self):
        forged = {**RTL_PROPOSAL, "evidence_ids": ["source:top.sv", "document:invented"]}
        document = {**RTL_PROPOSAL, "edits": [{"path": "design.md", "before": "y equals a", "after": "anything"}]}
        proposal, result, _ = self.run_proposals([forged, document, RTL_PROPOSAL])
        self.assertEqual(result.attempts, 3)
        self.assertEqual(proposal, RTL_PROPOSAL)

    def test_network_and_stage_policies_prevent_provider_calls(self):
        for network, stages in ((False, ("rtl_optimization",)), (True, ("physical_design",))):
            with self.subTest(network=network):
                proposal, result, client = self.run_proposals([], network=network, stages=stages)
                self.assertIsNone(proposal)
                self.assertEqual(result.attempts, 0)
                self.assertFalse(client.requests)

    def test_duplicate_experiment_and_stop(self):
        stop = {**deepcopy(RTL_PROPOSAL), "edits": None}
        proposal, result, _ = self.run_proposals([RTL_PROPOSAL, stop], history=[{"proposal": RTL_PROPOSAL}])
        self.assertEqual(result.attempts, 2)
        self.assertIsNone(proposal["edits"])

    def test_nine_view_requirements_metrics_ids_and_history_survive_factoring(self):
        measured = analysis()
        fields = ("setup_wns_ns", "hold_wns_ns", "cap_slack_percent", "slew_slack_percent")
        measured["scenarios"] = {}
        for pvt in ("tt_025C_1v80", "ss_100C_1v60", "ff_n40C_1v95"):
            for rc in ("min", "nom", "max"):
                name = f"functional_{pvt}_{rc}"
                metrics = {field: measured["metrics"][field] for field in fields}
                measured["scenarios"][name] = {"metrics": metrics, "clocks": measured["clocks"]}
                measured["metrics"].update({f"scenario:{name}:{field}": value for field, value in metrics.items()})
        measured["production_limits"] = {"area_max_um2": None, "power_max_watts": None}
        requirements = physical_requirements(measured)
        special = "scenario:functional_ss_100C_1v60_max:slew_slack_percent"
        requirements["metrics"][special]["target"] = 0.123456789012345
        assessment = assess_physical_requirements(requirements, measured)
        deltas = dict.fromkeys(measured["metrics"], 0.000000000123456)
        history = [
            {
                "iteration": index,
                "proposal": RTL_PROPOSAL,
                "selected": False,
                "proof_status": "equivalent",
                "metrics": deepcopy(measured["metrics"]),
                "evaluation": {
                    "assessment": deepcopy(assessment),
                    "metric_deltas": deepcopy(deltas),
                    "regressions": [special],
                    "improvements": [],
                },
            }
            for index in (1, 2)
        ]
        originals = deepcopy((measured, requirements, history))
        with TemporaryDirectory() as temporary:
            config = replace(
                default_config(Path(temporary)),
                allow_network=True,
                ai=AIConfig(model="fixture/rtl", allowed_stages=("rtl_optimization",), max_context_chars=100000),
            )
            client = Client([{**RTL_PROPOSAL, "edits": None}])
            sources = {"top.sv": "assign y = a & a;\n" + "// source preserved\n" * 1200}
            documents = {"design.md": "cycle-exact intent\n" * 600}
            _, result = propose_rtl_edit(
                LiteLLMGateway(config, client), sources, documents, measured, requirements, history, "area_um2"
            )
        self.assertEqual(result.status, "accepted")
        prompt = client.requests[0].user_prompt
        self.assertLessEqual(len(prompt), 100000)
        context = json.loads(prompt)
        self.assertEqual(context["sources"], sources)
        self.assertEqual(context["documents"], documents)
        self.assertEqual(context["analysis"]["paths"], measured["paths"])
        self.assertEqual(context["analysis"]["scenarios"], measured["scenarios"])
        factored = context["requirements"]["scenario_metrics"]["by_scenario"]
        expanded = dict(context["requirements"]["metrics"])
        for name, metrics in factored.items():
            expanded.update({f"scenario:{name}:{field}": gate for field, gate in metrics.items()})
        self.assertEqual(expanded, requirements["metrics"])
        self.assertEqual(context["requirements"]["clocks"], requirements["clocks"])
        expected_ids = {"source:top.sv", "document:design.md"} | {"metric:" + n for n in measured["metrics"]}
        expected_ids.update(path["evidence_id"] for path in measured["paths"])
        self.assertEqual(set(context["evidence_ids"]), expected_ids)
        for step in context["history"]:
            metrics = dict(step["metrics"])
            for name, values in step["scenario_metrics"].items():
                metrics.update({f"scenario:{name}:{field}": value for field, value in values.items()})
            self.assertEqual(metrics, measured["metrics"])
            evaluation = step["evaluation"]
            actual_deltas = dict(evaluation["metric_deltas"])
            for name, values in evaluation["scenario_metric_deltas"].items():
                actual_deltas.update({f"scenario:{name}:{field}": value for field, value in values.items()})
            self.assertEqual(actual_deltas, deltas)
            self.assertEqual(evaluation["regressions"], [special])
            self.assertEqual(evaluation["assessment"]["unmet_requirements"], assessment["unmet_requirements"])
            self.assertTrue(all(not check["met"] for check in evaluation["assessment"]["checks"].values()))
            self.assertEqual(step["proposal"], RTL_PROPOSAL)
        self.assertEqual((measured, requirements, history), originals)

    def test_oversized_required_source_is_rejected_before_a_provider_call(self):
        with TemporaryDirectory() as temporary:
            config = replace(
                default_config(Path(temporary)),
                allow_network=True,
                ai=AIConfig(model="fixture/rtl", allowed_stages=("rtl_optimization",), max_context_chars=4096),
            )
            client = Client([])
            with self.assertRaisesRegex(ValueError, "context exceeds"):
                propose_rtl_edit(
                    LiteLLMGateway(config, client),
                    {"top.sv": "x" * 5000},
                    {"design.md": "intent"},
                    analysis(),
                    physical_requirements(analysis()),
                    [],
                    "area_um2",
                )
            self.assertFalse(client.requests)
