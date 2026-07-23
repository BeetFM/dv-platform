import ast
import unittest
from dataclasses import replace

from dv_platform.analysis.depth import validate_depth_policies
from dv_platform.analysis.planner import create_initial_plan
from dv_platform.analysis.rtl import _cdc_paths
from dv_platform.analysis.scenarios import _cdc_scenarios
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    RTLCDCPath,
    RTLControlDomain,
    RTLExpression,
    RTLModule,
    RTLPort,
    RTLProceduralBlock,
    VerificationDepthPolicy,
    VerificationTarget,
)
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.formal import FormalGenerator


def _assignment(source: str, destination: str) -> RTLExpression:
    return RTLExpression(
        "assigndly",
        children=(RTLExpression("varref", name=source), RTLExpression("varref", name=destination)),
    )


def _module(paths: tuple[RTLCDCPath, ...]) -> RTLModule:
    evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcdc.xml", "procedure:cdc.dst"),)
    names = {
        "dst_clk": "input",
        "src_clk": "input",
        "rst_n": "input",
        "async_event": "input",
        "event_meta": "output",
        "event_sync": "output",
        "ack_async": "input",
        "ack_meta": "output",
        "ack_sync": "output",
        "payload": "input",
    }
    return RTLModule(
        "cdc",
        ports=tuple(names),
        port_details=tuple(RTLPort(name, direction) for name, direction in names.items()),
        control_domains=(
            RTLControlDomain("src", "src_clk", reset="rst_n", reset_active_low=True),
            RTLControlDomain("dst", "dst_clk", reset="rst_n", reset_active_low=True),
        ),
        cdc_paths=paths,
        ast_refs=evidence,
    )


def _path(
    signal: str = "async_event", destination: str = "dst", stages: tuple[str, ...] = ("event_meta", "event_sync")
):
    evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcdc.xml", "procedure:cdc.dst"),)
    return RTLCDCPath(
        f"cdc:{signal}:{destination}",
        signal,
        "external",
        destination,
        "two_flop",
        len(stages),
        stages,
        True,
        True,
        evidence_refs=evidence,
    )


class CDCSchemeQualificationTests(unittest.TestCase):
    def test_scenario_construction_fails_closed_for_incomplete_plan_facts(self) -> None:
        policy = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (("structure", "toggle"), ("output_signal", "event_sync")),
        )
        plan = create_initial_plan(
            _module((_path(),)),
            (VerificationTarget.COCOTB,),
            depth_policies=(policy,),
        )
        wrong_output = replace(
            plan,
            depth_policies=(replace(policy, parameters=(("structure", "toggle"), ("output_signal", "wrong"))),),
        )
        self.assertEqual(_cdc_scenarios(wrong_output), [])
        self.assertEqual(_cdc_scenarios(replace(plan, control_domains=())), [])
        self.assertEqual(_cdc_scenarios(replace(plan, check_details=())), [])

        handshake = replace(
            plan,
            cdc_paths=(replace(_path(), classification="handshake"),),
            depth_policies=(
                VerificationDepthPolicy(
                    "cdc",
                    "cdc",
                    "async_event",
                    (
                        ("structure", "handshake"),
                        ("output_signal", "event_sync"),
                        ("ack_input_signal", "ack_async"),
                        ("ack_output_signal", "ack_sync"),
                    ),
                ),
            ),
        )
        self.assertEqual(_cdc_scenarios(handshake), [])

    def test_external_input_two_flop_chain_is_normalized(self) -> None:
        domain = RTLControlDomain("dst", "dst_clk", reset="rst_n", reset_active_low=True)
        block = RTLProceduralBlock(
            "always_ff",
            domain_id="dst",
            expressions=(_assignment("async_event", "event_meta"), _assignment("event_meta", "event_sync")),
        )

        paths = _cdc_paths(
            "cdc",
            (block,),
            (domain,),
            (EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcdc.xml", "procedure:cdc.dst"),),
            (
                RTLPort("dst_clk", "input"),
                RTLPort("rst_n", "input"),
                RTLPort("async_event", "input"),
                RTLPort("event_sync", "output"),
            ),
        )

        self.assertEqual(len(paths), 1)
        self.assertEqual(paths[0].source_domain, "external")
        self.assertEqual(paths[0].classification, "two_flop")
        self.assertEqual(paths[0].stage_signals, ("event_meta", "event_sync"))

    def test_toggle_and_pulse_policies_create_executable_cocotb_and_formal_scenarios(self) -> None:
        for structure, extra, expected in (
            ("toggle", (), "toggle rise did not propagate"),
            ("pulse", (("pulse_stretch_cycles", "2"),), "stretched pulse was not observed"),
        ):
            with self.subTest(structure=structure):
                policy = VerificationDepthPolicy(
                    "cdc",
                    "cdc",
                    "async_event",
                    (
                        ("structure", structure),
                        ("output_signal", "event_sync"),
                        ("max_latency_cycles", "5"),
                        *extra,
                    ),
                )
                plan = create_initial_plan(
                    _module((_path(),)),
                    (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                    depth_policies=(policy,),
                )

                scenario = next(item for item in plan.scenarios if item.kind == f"cdc_{structure}")
                self.assertTrue(scenario.executable)
                self.assertEqual(
                    set(scenario.supported_targets), {VerificationTarget.COCOTB, VerificationTarget.FORMAL}
                )
                cocotb = CocotbGenerator().generate(plan)[0].content
                ast.parse(cocotb)
                self.assertIn(expected, cocotb)
                formal = FormalGenerator("structural").generate(plan)[0].content
                self.assertIn(f"c_cdc_cdc_async_event_dst_{structure}", formal)

    def test_handshake_requires_and_renders_a_qualified_reverse_path(self) -> None:
        request = _path()
        acknowledgement = _path("ack_async", "src", ("ack_meta", "ack_sync"))
        policy = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (
                ("structure", "handshake"),
                ("output_signal", "event_sync"),
                ("ack_input_signal", "ack_async"),
                ("ack_output_signal", "ack_sync"),
                ("data_signals", "payload"),
                ("max_latency_cycles", "5"),
            ),
        )
        module = _module((request, acknowledgement))
        plan = create_initial_plan(
            module,
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=(policy,),
        )

        self.assertEqual(str(validate_depth_policies(module, (policy,))[0].status), "supported")
        self.assertTrue(any(item.kind == "cdc_handshake" and item.executable for item in plan.scenarios))
        cocotb = CocotbGenerator().generate(plan)[0].content
        self.assertIn("acknowledgement did not return", cocotb)
        formal = FormalGenerator("structural").generate(plan)[0].content
        self.assertIn("a_cdc_cdc_async_event_dst_request_held: assume", formal)
        self.assertIn("a_cdc_cdc_async_event_dst_data_stable_0: assume", formal)
        self.assertIn("c_cdc_cdc_async_event_dst_round_trip", formal)

        missing_ack = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (("structure", "handshake"), ("output_signal", "event_sync")),
        )
        self.assertEqual(str(validate_depth_policies(module, (missing_ack,))[0].status), "missing_evidence")

    def test_short_pulse_and_wrong_output_fail_closed(self) -> None:
        module = _module((_path(),))
        short = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (
                ("structure", "pulse"),
                ("output_signal", "event_sync"),
                ("pulse_stretch_cycles", "1"),
            ),
        )
        wrong = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (("structure", "toggle"), ("output_signal", "wrong")),
        )

        self.assertEqual(str(validate_depth_policies(module, (short,))[0].status), "contradicted")
        self.assertEqual(str(validate_depth_policies(module, (wrong,))[0].status), "contradicted")

    def test_gray_counter_policy_is_executable_and_width_checked(self) -> None:
        module = _module((replace(_path(), classification="gray"),))
        ports = tuple(
            replace(port, width=4) if port.name in {"async_event", "event_sync"} else port
            for port in module.port_details
        )
        module = replace(module, port_details=ports)
        policy = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (
                ("structure", "gray"),
                ("output_signal", "event_sync"),
                ("max_latency_cycles", "5"),
                ("max_source_steps_per_destination", "1"),
            ),
        )
        plan = create_initial_plan(
            module,
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=(policy,),
        )

        self.assertEqual(str(validate_depth_policies(module, (policy,))[0].status), "supported")
        scenario = next(item for item in plan.scenarios if item.kind == "cdc_gray")
        self.assertEqual(dict(scenario.stimulus[0].parameters)["data_width"], "4")
        cocotb = CocotbGenerator().generate(plan)[0].content
        ast.parse(cocotb)
        self.assertIn("synchronized Gray counter changed by more than one bit", cocotb)
        formal = FormalGenerator("structural").generate(plan)[0].content
        self.assertIn("a_cdc_cdc_async_event_dst_gray_one_bit", formal)

        mismatched = replace(
            module,
            port_details=tuple(
                replace(port, width=3) if port.name == "event_sync" else port for port in module.port_details
            ),
        )
        self.assertEqual(str(validate_depth_policies(mismatched, (policy,))[0].status), "contradicted")
        unbounded = replace(
            policy,
            parameters=tuple(item for item in policy.parameters if item[0] != "max_source_steps_per_destination"),
        )
        self.assertEqual(str(validate_depth_policies(module, (unbounded,))[0].status), "missing_evidence")

    def test_multi_bit_handshake_checks_destination_payload_coherency(self) -> None:
        request = replace(_path(), classification="handshake")
        acknowledgement = _path("ack_async", "src", ("ack_meta", "ack_sync"))
        module = _module((request, acknowledgement))
        directions = {port.name: port.direction for port in module.port_details}
        directions["payload_observed"] = "output"
        module = replace(
            module,
            ports=(*module.ports, "payload_observed"),
            port_details=tuple(
                RTLPort(name, direction, width=16 if name in {"payload", "payload_observed"} else None)
                for name, direction in directions.items()
            ),
        )
        policy = VerificationDepthPolicy(
            "cdc",
            "cdc",
            "async_event",
            (
                ("structure", "multi_bit_handshake"),
                ("output_signal", "event_sync"),
                ("ack_input_signal", "ack_async"),
                ("ack_output_signal", "ack_sync"),
                ("data_signals", "payload"),
                ("observed_data_signals", "payload_observed"),
                ("max_latency_cycles", "5"),
            ),
        )
        plan = create_initial_plan(
            module,
            (VerificationTarget.COCOTB, VerificationTarget.FORMAL),
            depth_policies=(policy,),
        )

        self.assertEqual(str(validate_depth_policies(module, (policy,))[0].status), "supported")
        self.assertTrue(any(item.kind == "cdc_multi_bit_handshake" for item in plan.scenarios))
        cocotb = CocotbGenerator().generate(plan)[0].content
        ast.parse(cocotb)
        self.assertIn("multi-bit payload 0 was not transferred coherently", cocotb)
        formal = FormalGenerator("structural").generate(plan)[0].content
        self.assertIn("a_cdc_cdc_async_event_dst_payload_coherent_0", formal)

        incomplete = replace(
            policy,
            parameters=tuple(item for item in policy.parameters if item[0] != "observed_data_signals"),
        )
        self.assertEqual(str(validate_depth_policies(module, (incomplete,))[0].status), "missing_evidence")
