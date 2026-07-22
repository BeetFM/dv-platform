import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.depth import build_depth_checks, validate_depth_policies
from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.core.config import default_config, load_config, validate_config, write_config
from dv_platform.core.models import (
    FormalToolConfig,
    RTLCDCPath,
    RTLControlDomain,
    RTLMemory,
    RTLMemoryAccess,
    RTLModule,
    RTLPort,
    RTLProtocol,
    VerificationCheck,
    VerificationDepthPolicy,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.formal import FormalGenerator
from dv_platform.run import FormalResults, _formal_check_statuses, prepare_formal_run


class VerificationDepthTests(unittest.TestCase):
    def test_depth_policy_round_trips_configuration_and_plan_schema(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            policy = VerificationDepthPolicy(
                kind="memory",
                module="fifo",
                subject="storage",
                parameters=(("initialization", "unconstrained"), ("read_during_write", "read_first")),
            )
            config = replace(default_config(repo), depth_policies=(policy,))
            config_path = repo / "dv-platform.toml"

            write_config(config, config_path)
            loaded = load_config(config_path)
            write_plan_outputs(
                loaded,
                (VerificationPlan("fifo", (VerificationTarget.FORMAL,), depth_policies=loaded.depth_policies),),
            )
            stored = read_stored_plans(loaded.work_dir / "plans" / "plans.sqlite")[0]

            self.assertEqual(loaded.depth_policies, (policy,))
            self.assertEqual(stored.depth_policies, (policy,))

    def test_depth_policy_validation_rejects_unsafe_values(self) -> None:
        with TemporaryDirectory() as temp_dir:
            policy = VerificationDepthPolicy(
                kind="cdc",
                module="bridge",
                subject="status",
                parameters=(("min_stages", "1"), ("structure", "guess"), ("unknown", "value")),
            )
            config = replace(default_config(Path(temp_dir)), depth_policies=(policy, policy))

            messages = tuple(diagnostic.message for diagnostic in validate_config(config))

            self.assertTrue(any("Duplicate verification depth policy" in message for message in messages))
            self.assertTrue(any("Unsupported cdc verification parameters" in message for message in messages))
            self.assertTrue(any("Invalid CDC structure" in message for message in messages))
            self.assertTrue(any("min_stages" in message for message in messages))

    def test_depth_checks_cover_structural_and_configured_intent(self) -> None:
        module = RTLModule(
            name="fifo",
            memories=(RTLMemory("storage", depth=4),),
            memory_accesses=(
                RTLMemoryAccess(
                    "write:storage",
                    "storage",
                    "write",
                    address_signals=("wr_addr",),
                    data_signals=("wr_data",),
                    enable_signals=("wr_en",),
                    synchronous=True,
                ),
            ),
            control_domains=(RTLControlDomain("main", "clk", reset="rst_n", asynchronous_reset=True),),
            protocols=(RTLProtocol("rv:out", "ready_valid", "out", "source", "out_valid", "out_ready"),),
            cdc_paths=(RTLCDCPath("cdc:status", "status", "write", "read", safe=False),),
        )
        policies = (
            VerificationDepthPolicy("memory", "fifo", "storage", (("read_during_write", "write_first"),)),
            VerificationDepthPolicy("cdc", "fifo", "status", (("structure", "two_flop"), ("max_latency_cycles", "3"))),
        )

        checks = build_depth_checks(module, policies)

        self.assertTrue(any("reset rst_n assertion and release" in check for check in checks))
        self.assertTrue(any("lowest and highest legal addresses" in check for check in checks))
        self.assertTrue(any("backpressure followed by a successful transfer" in check for check in checks))
        self.assertTrue(any("read-during-write behavior is write_first" in check for check in checks))
        self.assertTrue(any("two_flop structure" in check for check in checks))

    def test_formal_generator_emits_configured_memory_collision_property(self) -> None:
        policy = VerificationDepthPolicy("memory", "fifo", "storage", (("read_during_write", "write_first"),))
        plan = VerificationPlan(
            module="fifo",
            targets=(VerificationTarget.FORMAL,),
            ports=(
                RTLPort("clk", "input"),
                RTLPort("rd_addr", "input", width=2),
                RTLPort("wr_addr", "input", width=2),
                RTLPort("wr_data", "input", width=8),
                RTLPort("wr_en", "input"),
                RTLPort("rd_data", "output", width=8),
            ),
            memories=(RTLMemory("storage", depth=4, element_width=8),),
            memory_accesses=(
                RTLMemoryAccess(
                    "read:storage",
                    "storage",
                    "read",
                    address_signals=("rd_addr",),
                    data_signals=("rd_data",),
                    synchronous=True,
                ),
                RTLMemoryAccess(
                    "write:storage",
                    "storage",
                    "write",
                    address_signals=("wr_addr",),
                    data_signals=("wr_data",),
                    enable_signals=("wr_en",),
                    synchronous=True,
                ),
            ),
            depth_policies=(policy,),
        )

        harness = FormalGenerator().generate(plan)[0].content

        self.assertIn("a_memory_collision_1_1: assert(rd_data == $past(wr_data));", harness)
        self.assertIn("c_memory_collision_1_1: cover", harness)

    def test_cdc_policy_conformance_supports_chain_and_contradicts_stage_shortfall(self) -> None:
        module = RTLModule(
            name="bridge",
            cdc_paths=(
                RTLCDCPath(
                    "bridge:cdc:status",
                    "status",
                    "write",
                    "read",
                    classification="two_flop",
                    synchronizer_stages=2,
                    stage_signals=("status_meta", "status_sync"),
                    safe=True,
                    reset_compatible=True,
                ),
            ),
        )
        supported = VerificationDepthPolicy(
            "cdc",
            "bridge",
            "status",
            (("min_stages", "2"), ("reset_compatible", "true"), ("structure", "two_flop")),
        )
        contradicted = VerificationDepthPolicy(
            "cdc", "bridge", "status", (("min_stages", "3"), ("structure", "two_flop"))
        )

        supported_claim = validate_depth_policies(module, (supported,))[0]
        contradicted_claim = validate_depth_policies(module, (contradicted,))[0]

        self.assertEqual(str(supported_claim.status), "supported")
        self.assertEqual(str(supported_claim.evidence_refs[0].kind), "configuration")
        self.assertEqual(str(contradicted_claim.status), "contradicted")

    def test_formal_prove_and_cover_tasks_are_attributed_independently(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            plan = VerificationPlan(
                "fifo",
                (VerificationTarget.FORMAL,),
                check_details=(
                    VerificationCheck("fifo:check:assert", "Verify output stability.", executable=True),
                    VerificationCheck("fifo:check:cover", "Cover backpressure recovery.", executable=True),
                ),
            )
            write_plan_outputs(config, (plan,))
            run = prepare_formal_run(config, FormalToolConfig("symbiyosys", "sby"), "fifo")

            statuses = _formal_check_statuses(
                run,
                FormalResults(formal_status="fail", task_status={"prove": "pass", "cover": "fail"}),
            )

            self.assertEqual(
                statuses,
                {"fifo:check:assert": "passed", "fifo:check:cover": "failed"},
            )


if __name__ == "__main__":
    unittest.main()
