from pathlib import Path
from shutil import which
from subprocess import run
from tempfile import TemporaryDirectory
from unittest import TestCase, skipUnless

from dv_platform.core.models import (
    RTLCDCPath,
    RTLClock,
    RTLControlDomain,
    RTLPort,
    RTLReset,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.formal import FormalGenerator


@skipUnless(which("sby") and which("z3"), "SymbiYosys and Z3 are required")
class CDCFormalIntegrationTests(TestCase):
    def test_generated_multiclock_harness_proves_two_stage_synchronizer(self) -> None:
        plan = VerificationPlan(
            module="bridge",
            design_unit="bridge",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort(name="src_clk", direction="input"),
                RTLPort(name="dst_clk", direction="input"),
                RTLPort(name="dst_rst_n", direction="input"),
                RTLPort(name="async_req", direction="input"),
                RTLPort(name="sync_req", direction="output"),
            ),
            clocks=(
                RTLClock(name="src_clk", direction="input"),
                RTLClock(name="dst_clk", direction="input"),
            ),
            resets=(
                RTLReset(
                    name="dst_rst_n",
                    direction="input",
                    active_low=True,
                ),
            ),
            control_domains=(
                RTLControlDomain(
                    domain_id="dst",
                    clock="dst_clk",
                    reset="dst_rst_n",
                    reset_active_low=True,
                    asynchronous_reset=True,
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
        rtl = """\
module bridge (
    input logic src_clk,
    input logic dst_clk,
    input logic dst_rst_n,
    input logic async_req,
    output logic sync_req
);
    logic sync_meta;
    always_ff @(posedge dst_clk or negedge dst_rst_n) begin
        if (!dst_rst_n) begin
            sync_meta <= 1'b0;
            sync_req <= 1'b0;
        end else begin
            sync_meta <= async_req;
            sync_req <= sync_meta;
        end
    end
endmodule
"""

        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = FormalGenerator(cdc_policy="bounded", cdc_bmc_depth=12).generate(plan)
            harness = next(artifact.content for artifact in artifacts if artifact.path.name == "formal_bridge.sv")
            self.assertNotIn("dut.sync_meta", harness)
            self.assertIn(
                "a_cdc_async_req_to_dst_bounded: assert(sync_req == cdc_async_req_to_dst_history[1]);",
                harness,
            )
            sby = next(artifact.content for artifact in artifacts if artifact.path.suffix == ".sby")
            self.assertIn("cdc_bmc: mode bmc", sby)
            self.assertIn("-D DV_CDC_BOUNDED", sby)
            for artifact in artifacts:
                content = artifact.content
                if artifact.path.suffix == ".sby":
                    content = (
                        content.replace(
                            "read -formal formal_bridge.sv",
                            "read -formal bridge.sv formal_bridge.sv",
                        )
                        .replace(
                            "read -formal -D DV_CDC_BOUNDED formal_bridge.sv",
                            "read -formal -D DV_CDC_BOUNDED bridge.sv formal_bridge.sv",
                        )
                        .replace(
                            "[files]\nformal_bridge.sv",
                            "[files]\nbridge.sv\nformal_bridge.sv",
                        )
                    )
                (root / artifact.path).write_text(content, encoding="utf-8")
            (root / "bridge.sv").write_text(rtl, encoding="utf-8")

            completed = run(
                ["sby", "-f", "bridge.sby"],
                cwd=root,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )

    def test_structural_policy_proves_each_observable_stage(self) -> None:
        plan = VerificationPlan(
            module="bridge_observable",
            design_unit="bridge_observable",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort("dst_clk", "input"),
                RTLPort("dst_rst_n", "input"),
                RTLPort("async_req", "input"),
                RTLPort("sync_meta", "output"),
                RTLPort("sync_req", "output"),
            ),
            clocks=(RTLClock("dst_clk", "input"),),
            resets=(RTLReset("dst_rst_n", "input", active_low=True),),
            control_domains=(
                RTLControlDomain(
                    domain_id="dst",
                    clock="dst_clk",
                    reset="dst_rst_n",
                    reset_active_low=True,
                    asynchronous_reset=True,
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
        rtl = """\
module bridge_observable (
    input logic dst_clk,
    input logic dst_rst_n,
    input logic async_req,
    output logic sync_meta,
    output logic sync_req
);
    always_ff @(posedge dst_clk or negedge dst_rst_n) begin
        if (!dst_rst_n) begin
            sync_meta <= 1'b0;
            sync_req <= 1'b0;
        end else begin
            sync_meta <= async_req;
            sync_req <= sync_meta;
        end
    end
endmodule
"""

        with TemporaryDirectory() as directory:
            root = Path(directory)
            artifacts = FormalGenerator(cdc_policy="structural").generate(plan)
            harness = next(artifact.content for artifact in artifacts if artifact.path.suffix == ".sv")
            self.assertIn("a_cdc_async_req_to_dst_stage_0", harness)
            self.assertIn("a_cdc_async_req_to_dst_stage_1", harness)
            for artifact in artifacts:
                content = artifact.content
                if artifact.path.suffix == ".sby":
                    content = content.replace(
                        "read -formal formal_bridge_observable.sv",
                        "read -formal bridge_observable.sv formal_bridge_observable.sv",
                    ).replace(
                        "[files]\nformal_bridge_observable.sv",
                        "[files]\nbridge_observable.sv\nformal_bridge_observable.sv",
                    )
                (root / artifact.path).write_text(content, encoding="utf-8")
            (root / "bridge_observable.sv").write_text(rtl, encoding="utf-8")

            completed = run(
                ["sby", "-f", "bridge_observable.sby"],
                cwd=root,
                capture_output=True,
                check=False,
                text=True,
                timeout=30,
            )

        self.assertEqual(
            completed.returncode,
            0,
            msg=f"stdout:\n{completed.stdout}\nstderr:\n{completed.stderr}",
        )
