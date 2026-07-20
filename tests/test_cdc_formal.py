from unittest import TestCase

from dv_platform.core.models import (
    RTLCDCPath,
    RTLControlDomain,
    RTLPort,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.formal import CDCProofPolicy, FormalGenerator, _cdc_assertions


class CDCFormalGenerationTests(TestCase):
    def test_fail_closed_reports_hidden_stages_without_generating_properties(self) -> None:
        plan = VerificationPlan(
            module="bridge",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort(name="dst_clk", direction="input"),
                RTLPort(name="dst_rst_n", direction="input"),
                RTLPort(name="async_req", direction="input"),
            ),
            control_domains=(
                RTLControlDomain(
                    domain_id="dst",
                    clock="dst_clk",
                    reset="dst_rst_n",
                    reset_active_low=True,
                ),
            ),
            cdc_paths=(
                RTLCDCPath(
                    path_id="async_req_to_dst",
                    signal="async_req",
                    source_domain="src",
                    destination_domain="dst",
                    classification="two_flop",
                    synchronizer_stages=2,
                    stage_signals=("sync_meta", "sync_req"),
                    safe=True,
                    reset_compatible=True,
                ),
            ),
        )

        artifacts = FormalGenerator().generate(plan)
        content = artifacts[0].content
        report = next(artifact.content for artifact in artifacts if artifact.path.suffix == ".json")

        self.assertNotIn("a_cdc_async_req_to_dst", content)
        self.assertIn('"evidence_level": "unsupported"', report)
        self.assertIn('"hidden_stages": [', report)

    def test_structural_policy_generates_stage_properties_for_observable_stages(self) -> None:
        plan = VerificationPlan(
            module="bridge",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort(name="dst_clk", direction="input"),
                RTLPort(name="dst_rst_n", direction="input"),
                RTLPort(name="async_req", direction="input"),
                RTLPort(name="sync_meta", direction="output"),
                RTLPort(name="sync_req", direction="output"),
            ),
            control_domains=(
                RTLControlDomain(
                    domain_id="dst",
                    clock="dst_clk",
                    reset="dst_rst_n",
                    reset_active_low=True,
                ),
            ),
            cdc_paths=(
                RTLCDCPath(
                    path_id="async_req_to_dst",
                    signal="async_req",
                    source_domain="src",
                    destination_domain="dst",
                    classification="two_flop",
                    synchronizer_stages=2,
                    stage_signals=("sync_meta", "sync_req"),
                    safe=True,
                    reset_compatible=True,
                ),
            ),
        )

        artifacts = FormalGenerator(CDCProofPolicy.STRUCTURAL).generate(plan)
        content = artifacts[0].content
        sby = next(artifact.content for artifact in artifacts if artifact.path.suffix == ".sby")

        self.assertIn("(* gclk *) reg dv_formal_clock;", content)
        self.assertIn("always @(posedge dv_formal_clock)", content)
        self.assertIn("cdc_async_req_to_dst_expected[0] <= async_req;", content)
        self.assertIn("assert(sync_meta == cdc_async_req_to_dst_expected[0]);", content)
        self.assertIn("assert(sync_req == cdc_async_req_to_dst_expected[1]);", content)
        self.assertIn("multiclock on", sby)

    def test_structural_policy_rejects_hidden_stages(self) -> None:
        plan = VerificationPlan(
            module="bridge",
            targets=(VerificationTarget.FORMAL,),
            ports=(RTLPort("dst_clk", "input"), RTLPort("async_req", "input"), RTLPort("sync_req", "output")),
            control_domains=(RTLControlDomain("dst", "dst_clk"),),
            cdc_paths=(
                RTLCDCPath(
                    path_id="path",
                    signal="async_req",
                    source_domain="src",
                    destination_domain="dst",
                    classification="two_flop",
                    synchronizer_stages=2,
                    stage_signals=("meta", "sync_req"),
                    safe=True,
                ),
            ),
        )

        with self.assertRaisesRegex(ValueError, "Structural CDC policy requirements are not met"):
            FormalGenerator(CDCProofPolicy.STRUCTURAL).generate(plan)

    def test_skips_unsafe_incomplete_and_reset_incompatible_paths(self) -> None:
        common = {
            "signal": "async_req",
            "source_domain": "src",
            "destination_domain": "dst",
            "classification": "two_flop",
            "synchronizer_stages": 2,
        }
        paths = (
            RTLCDCPath(
                path_id="unsafe",
                safe=False,
                stage_signals=("sync_meta", "sync_req"),
                **common,
            ),
            RTLCDCPath(
                path_id="incomplete",
                safe=True,
                stage_signals=("sync_meta",),
                **common,
            ),
            RTLCDCPath(
                path_id="reset_mismatch",
                safe=True,
                reset_compatible=False,
                stage_signals=("sync_meta", "sync_req"),
                **common,
            ),
        )
        plan = VerificationPlan(
            module="bridge",
            targets=(VerificationTarget.FORMAL,),
            control_domains=(RTLControlDomain(domain_id="dst", clock="dst_clk"),),
            cdc_paths=paths,
        )

        self.assertEqual(_cdc_assertions(plan), [])
