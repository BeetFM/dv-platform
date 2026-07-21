import unittest

from dv_platform.agent.protocols import (
    ProtocolChannel,
    ProtocolModel,
    RegisterConflict,
    RegisterField,
    RegisterModel,
    ahb_lite_model,
    apb4_model,
    axi4_lite_model,
)
from dv_platform.core.models import EvidenceKind, EvidenceRef


class ProtocolContractBranchTests(unittest.TestCase):
    def setUp(self) -> None:
        self.source_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "E1", "module:top")
        self.locator_ref = EvidenceRef(EvidenceKind.CONFIGURATION, "config", "CFG1")

    def test_protocol_evidence_accepts_source_or_locator_and_rejects_unknown(self) -> None:
        channel = ProtocolChannel("transfer", ("valid",), "source", "valid", (self.locator_ref,))
        model = ProtocolModel("test", "1", (channel,), (("valid", "valid"),), evidence_refs=(self.source_ref,))

        model.validate({"E1", "CFG1"})
        with self.assertRaisesRegex(ValueError, "outside task context"):
            model.validate({"E1"})

    def test_register_geometry_failure_matrix(self) -> None:
        invalid = (
            RegisterModel("r", 0, 0, evidence_refs=(self.source_ref,), source="config"),
            RegisterModel("r", -1, 32, evidence_refs=(self.source_ref,), source="config"),
            RegisterModel("r", 0, 32, (RegisterField("f", 0, 1),), source="config", evidence_refs=(self.source_ref,)),
            RegisterModel("r", 0, 32, (RegisterField("f", 1, -1),), source="config", evidence_refs=(self.source_ref,)),
            RegisterModel("r", 0, 32, (RegisterField("f", 32, 0),), source="config", evidence_refs=(self.source_ref,)),
        )
        for register in invalid:
            with self.subTest(register=register), self.assertRaisesRegex(ValueError, "width or field range"):
                register.validate({"E1"})

    def test_register_unknown_and_evidence_failure_matrix(self) -> None:
        cases = (
            (RegisterModel("r", None, 32, source="config", evidence_refs=(self.source_ref,)), "unknown"),
            (RegisterModel("r", 0, 32, source="unknown", evidence_refs=(self.source_ref,)), "unknown"),
            (RegisterModel("r", 0, 32, source="config"), "requires evidence"),
            (RegisterModel("r", 0, 32, source="config", evidence_refs=(self.source_ref,)), "outside"),
        )
        for register, message in cases:
            with self.subTest(register=register), self.assertRaisesRegex(ValueError, message):
                register.validate(set())

        register = RegisterModel(
            "r",
            0,
            32,
            fields=(RegisterField("f", 7, 0, evidence_refs=(self.locator_ref,)),),
            source="config",
            evidence_refs=(self.source_ref,),
        )
        register.validate({"E1", "CFG1"})

    def test_register_conflict_requires_values_evidence_and_context(self) -> None:
        valid = RegisterConflict("r", "offset", ("0", "4"), "conflict", (self.source_ref,))
        valid.validate({"E1"})
        for conflict, message in (
            (RegisterConflict("r", "offset", (), "conflict", (self.source_ref,)), "require values"),
            (RegisterConflict("r", "offset", ("0",), "conflict"), "require values"),
            (valid, "outside"),
        ):
            with self.subTest(conflict=conflict), self.assertRaisesRegex(ValueError, message):
                conflict.validate(set())

    def test_protocol_constructors_filter_channels_to_available_bindings(self) -> None:
        axi = axi4_lite_model((("awvalid", "s_awvalid"), ("rready", "s_rready")), (self.source_ref,))
        apb = apb4_model((("psel", "s_psel"), ("pready", "s_pready")), (self.source_ref,))
        ahb = ahb_lite_model((("hsel", "s_hsel"), ("hresp", "s_hresp")), (self.source_ref,))

        self.assertEqual(axi.channels[0].signals, ("awvalid",))
        self.assertEqual(axi.channels[-1].signals, ("rready",))
        self.assertEqual(apb.channels[0].signals, ("psel", "pready"))
        self.assertEqual(ahb.channels[0].signals, ("hsel",))
        self.assertEqual(ahb.channels[-1].signals, ("hresp",))


if __name__ == "__main__":
    unittest.main()
