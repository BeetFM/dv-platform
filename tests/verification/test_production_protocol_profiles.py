import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.protocols import (
    ProtocolChannel,
    ProtocolModel,
    RegisterConflict,
    RegisterField,
    RegisterModel,
    production_protocol_profiles,
    protocol_profile,
    protocol_profile_from_json,
    protocol_profile_to_json,
)
from dv_platform.analysis.protocols import (
    recognize_production_protocols,
    recognize_protocol_profile,
    recognize_protocols,
)
from dv_platform.analysis.scenarios import build_deterministic_scenarios
from dv_platform.core.config import default_config, load_config, write_config
from dv_platform.core.models import (
    EvidenceKind,
    EvidenceRef,
    ProductionProtocolBinding,
    RTLClock,
    RTLModule,
    RTLPort,
    VerificationCheck,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generators.cocotb import CocotbGenerator
from dv_platform.generators.uvm import UvmGenerator


class ProductionProtocolProfileTests(unittest.TestCase):
    def test_catalog_is_complete_versioned_and_bounded(self) -> None:
        profiles = production_protocol_profiles()
        self.assertEqual(
            {profile.profile_id for profile in profiles},
            {
                "axi4-lite-1.0",
                "axi4-1.0",
                "axi4-stream-1.0",
                "wishbone-b4-1.0",
                "avalon-mm-1.0",
                "avalon-st-1.0",
                "ahb-1.0",
                "tilelink-ul-uh-1.0",
                "axi4-lite-two-outstanding-1.0",
                "ahb-lite-incr4-1.0",
                "apb5-pwakeup-1.0",
            },
        )
        for profile in profiles:
            with self.subTest(profile=profile.profile_id):
                profile.validate()
                self.assertEqual(profile.schema_version, 1)
                self.assertTrue(profile.scoreboard_keys)
                self.assertTrue(profile.coverage_bins)
                self.assertTrue(profile.formal_properties)
                self.assertTrue(profile.result_traces)

    def test_public_json_contract_round_trips_and_rejects_future_versions(self) -> None:
        profile = protocol_profile("axi4-1.0")
        payload = protocol_profile_to_json(profile)
        self.assertEqual(protocol_profile_from_json(payload), profile)
        payload["schema_version"] = 2
        with self.assertRaisesRegex(ValueError, "unsupported protocol profile schema version"):
            protocol_profile_from_json(payload)

    def test_public_protocol_contracts_fail_closed_on_malformed_inputs(self) -> None:
        base = protocol_profile("axi4-stream-1.0")
        invalid_profiles = (
            replace(base, profile_id=""),
            replace(base, maximum_outstanding=0),
            replace(base, signals=(*base.signals, base.signals[0])),
            replace(
                base,
                signals=(
                    replace(base.signals[0], aliases=("shared",)),
                    replace(base.signals[1], aliases=("shared",)),
                    *base.signals[2:],
                ),
            ),
            replace(base, signals=(replace(base.signals[0], direction="sideways"), *base.signals[1:])),
        )
        for profile in invalid_profiles:
            with self.subTest(profile=profile), self.assertRaises(ValueError):
                profile.validate()

        payload = protocol_profile_to_json(base)
        with self.assertRaisesRegex(ValueError, "signals must be an array"):
            protocol_profile_from_json({**payload, "signals": "invalid"})
        with self.assertRaisesRegex(ValueError, "invalid protocol profile"):
            protocol_profile_from_json({"signals": []})
        with self.assertRaisesRegex(ValueError, "signal entries must be objects"):
            protocol_profile_from_json({**payload, "signals": [*payload["signals"], "invalid"]})
        with self.assertRaisesRegex(ValueError, "unknown protocol profile"):
            protocol_profile("unknown-1.0")

        evidence = EvidenceRef(EvidenceKind.VERILATOR_AST, "ast", "module:top")
        channel = ProtocolChannel("request", ("valid",), "manager_to_subordinate", "valid", (evidence,))
        model = ProtocolModel(
            "test",
            "1.0",
            (channel,),
            (("valid", "valid_i"),),
            evidence_refs=(evidence,),
        )
        model.validate({"ast"})
        for invalid in (
            replace(model, timeout_cycles=0),
            replace(model, signal_bindings=(("valid", "a"), ("valid", "b"))),
            replace(model, signal_bindings=(("a", "same"), ("b", "same"))),
        ):
            with self.subTest(model=invalid), self.assertRaises(ValueError):
                invalid.validate({"ast"})
        with self.assertRaisesRegex(ValueError, "outside task context"):
            model.validate(set())

        conflict = RegisterConflict("control", "offset", ("0",), "conflict", (evidence,))
        conflict.validate({"ast"})
        with self.assertRaisesRegex(ValueError, "values and evidence"):
            replace(conflict, values=()).validate({"ast"})
        with self.assertRaisesRegex(ValueError, "outside task context"):
            conflict.validate(set())

    def test_packet_complete_axi_stream_recognition(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        ports = tuple(
            RTLPort(
                f"video_{signal.name}",
                "output" if signal.direction == "manager_to_subordinate" else "input",
                width=signal.width if isinstance(signal.width, int) else 32,
            )
            for signal in profile.signals
        )
        model = recognize_protocol_profile(RTLModule("top", port_details=ports), profile)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.role, "source")
        self.assertEqual(model.instance_id, "top:video")
        self.assertIn("packet_length", model.coverage_bins)
        self.assertIn(("tlast", "video_tlast"), model.signal_bindings)

    def test_partial_and_wrong_direction_interfaces_fail_closed(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        required = tuple(signal for signal in profile.signals if not signal.optional)
        partial = RTLModule(
            "partial",
            port_details=tuple(RTLPort(signal.name, "output") for signal in required[:-1]),
        )
        self.assertIsNone(recognize_protocol_profile(partial, profile))

        wrong = RTLModule(
            "wrong",
            port_details=tuple(RTLPort(signal.name, "output") for signal in profile.signals),
        )
        self.assertIsNone(recognize_protocol_profile(wrong, profile))

    def test_explicit_aliases_bind_nonstandard_names(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        aliases = tuple((signal.name, f"bus_{index}") for index, signal in enumerate(profile.signals))
        ports = tuple(
            RTLPort(
                physical,
                "input" if signal.direction == "manager_to_subordinate" else "output",
                width=signal.width if isinstance(signal.width, int) else 32,
            )
            for signal, (_canonical, physical) in zip(profile.signals, aliases, strict=True)
        )
        model = recognize_protocol_profile(RTLModule("top", port_details=ports), profile, aliases=aliases)
        self.assertIsNotNone(model)
        assert model is not None
        self.assertEqual(model.role, "sink")
        self.assertEqual(model.confidence, "explicit_alias")

    def test_full_axi_suppresses_lite_subset(self) -> None:
        profile = protocol_profile("axi4-1.0")
        ports = tuple(
            RTLPort(
                signal.name,
                "input" if signal.direction == "manager_to_subordinate" else "output",
                width=signal.width if isinstance(signal.width, int) else 32,
            )
            for signal in profile.signals
        )
        models = recognize_production_protocols(RTLModule("axi", port_details=ports))
        self.assertEqual([model.profile_id for model in models], ["axi4-1.0"])

    def test_ambiguous_multiple_instances_require_explicit_binding(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        ports = tuple(
            RTLPort(
                f"{prefix}_{signal.name}",
                "input" if signal.direction == "manager_to_subordinate" else "output",
            )
            for prefix in ("left", "right")
            for signal in profile.signals
        )
        with self.assertRaisesRegex(ValueError, "multiple AXI4-Stream instances"):
            recognize_protocol_profile(RTLModule("top", port_details=ports), profile)

    def test_configured_aliases_resolve_multiple_instances_and_round_trip(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        ports = tuple(
            RTLPort(
                f"{prefix}_{signal.name}",
                "input" if signal.direction == "manager_to_subordinate" else "output",
            )
            for prefix in ("left", "right")
            for signal in profile.signals
        )
        bindings = tuple(
            ProductionProtocolBinding(
                profile.profile_id,
                "top",
                prefix,
                "sink",
                tuple((signal.name, f"{prefix}_{signal.name}") for signal in profile.signals),
            )
            for prefix in ("left", "right")
        )
        models = recognize_protocols(RTLModule("top", port_details=ports), bindings)
        self.assertEqual({model.instance_id for model in models}, {"top:left", "top:right"})
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "dv-platform.toml"
            write_config(replace(default_config(root), production_protocol_bindings=bindings), path)
            loaded = load_config(path).production_protocol_bindings
            self.assertEqual(
                {(item.module, item.instance_id, item.role, frozenset(item.aliases)) for item in loaded},
                {(item.module, item.instance_id, item.role, frozenset(item.aliases)) for item in bindings},
            )

    def test_axi_stream_contract_builds_executable_cocotb_scenario(self) -> None:
        profile = protocol_profile("axi4-stream-1.0")
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "ast", "module:top"),)
        ports = tuple(
            RTLPort(
                signal.name,
                "input" if signal.direction == "manager_to_subordinate" else "output",
                width=signal.width if isinstance(signal.width, int) else 32,
            )
            for signal in profile.signals
        ) + (RTLPort("clk", "input"), RTLPort("reset_n", "input"))
        model = recognize_protocol_profile(
            RTLModule("top", port_details=ports, ast_refs=evidence), profile, role="sink"
        )
        assert model is not None
        model = model.__class__(**{**model.__dict__, "clock_domain": "clk", "reset_domain": "reset_n"})
        base = VerificationPlan(
            module="top",
            targets=(VerificationTarget.COCOTB,),
            ports=ports,
            clocks=(RTLClock("clk", "input"),),
            protocol_models=(model,),
            check_details=(VerificationCheck("CHK-STREAM", "protocol packet transfer", "protocol", True, evidence),),
        )
        scenarios = build_deterministic_scenarios(base)
        plan = base.__class__(**{**base.__dict__, "scenarios": scenarios})
        self.assertEqual(len(scenarios), 1)
        self.assertTrue(scenarios[0].executable)
        content = CocotbGenerator().generate(plan)[0].content
        compile(content, "generated.py", "exec")
        self.assertIn("non-vacuous bounded profile transaction completed", content)
        self.assertIn("validate_protocol_trace(profile_id, tuple(beats))", content)
        self.assertIn("result.completed > 0", content)
        uvm_plan = replace(
            plan,
            targets=(VerificationTarget.UVM,),
            register_models=(
                RegisterModel(
                    "control",
                    0x10,
                    32,
                    (
                        RegisterField("enable", 0, 0, "1'b0", "rw"),
                        RegisterField("status", 7, 1, "7'h0", "ro"),
                    ),
                    source="test",
                    evidence_refs=evidence,
                ),
            ),
        )
        uvm = UvmGenerator().generate(uvm_plan)[0].content
        self.assertIn("class top_p0_driver extends uvm_driver", uvm)
        self.assertIn("class top_p0_scoreboard extends uvm_component", uvm)
        self.assertIn("covergroup protocol_cg", uvm)
        self.assertIn("cp_backpressure", uvm)
        self.assertIn("cp_tkeep: coverpoint tr.tkeep", uvm)
        self.assertIn("cp_tid: coverpoint tr.tid", uvm)
        self.assertIn("mask_x_packet: cross cp_tkeep, cp_tlast", uvm)
        self.assertIn("route_x_packet: cross cp_tid, cp_tlast", uvm)
        self.assertIn('enable.configure(this, 1, 0, "RW"', uvm)
        self.assertIn('status.configure(this, 7, 1, "RO"', uvm)
        self.assertIn("class top_reg_block extends uvm_reg_block", uvm)
        self.assertIn('default_map.add_reg(control, \'h10, "RW")', uvm)

        fallback_plan = replace(
            base,
            check_details=(VerificationCheck("CHK-OTHER", "bounded transfer", "other", True, evidence),),
        )
        fallback_scenario = build_deterministic_scenarios(fallback_plan)[0]
        self.assertEqual(fallback_scenario.check_ids, ("CHK-OTHER",))
        incomplete = replace(fallback_plan, protocol_models=(replace(model, unsupported_semantics=("unknown",)),))
        unsupported = build_deterministic_scenarios(incomplete)[0]
        self.assertFalse(unsupported.executable)
        self.assertFalse(unsupported.supported_targets)

    def test_avalon_mm_acceptance_uses_active_high_waitrequest_as_stall(self) -> None:
        profile = protocol_profile("avalon-mm-1.0")
        evidence = (EvidenceRef(EvidenceKind.VERILATOR_AST, "ast", "module:mm"),)
        ports = tuple(
            RTLPort(
                signal.name,
                "input" if signal.direction == "manager_to_subordinate" else "output",
                width=signal.width if isinstance(signal.width, int) else 32,
            )
            for signal in profile.signals
        ) + (RTLPort("clk", "input"), RTLPort("reset_n", "input"))
        model = recognize_protocol_profile(
            RTLModule("mm", port_details=ports, ast_refs=evidence), profile, role="agent"
        )
        assert model is not None
        model = model.__class__(**{**model.__dict__, "clock_domain": "clk", "reset_domain": "reset_n"})
        base = VerificationPlan(
            module="mm",
            targets=(VerificationTarget.COCOTB,),
            ports=ports,
            clocks=(RTLClock("clk", "input"),),
            protocol_models=(model,),
            check_details=(VerificationCheck("CHK-MM", "protocol transfer", "protocol", True, evidence),),
        )
        plan = base.__class__(**{**base.__dict__, "scenarios": build_deterministic_scenarios(base)})
        content = CocotbGenerator().generate(plan)[0].content
        self.assertIn("'waitrequest', 0", content)
        self.assertIn("'read_response'", content)
        self.assertIn("response_required", content)


if __name__ == "__main__":
    unittest.main()
