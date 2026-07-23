import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.protocols import RegisterField, RegisterModel, axi4_lite_model
from dv_platform.analysis.plan_store import read_stored_plans, write_plan_outputs
from dv_platform.core.config import default_config
from dv_platform.core.models import EvidenceKind, EvidenceRef, VerificationPlan, VerificationTarget


class ProtocolPlanStoreTests(unittest.TestCase):
    def test_protocol_and_register_models_round_trip(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            evidence = (EvidenceRef(EvidenceKind.CONFIGURATION, "cfg", "protocols.axi"),)
            protocol = axi4_lite_model((("awvalid", "s_awvalid"),), evidence)
            register = RegisterModel(
                "CONTROL",
                0,
                32,
                (RegisterField("ENABLE", 0, 0, "0", "rw", evidence_refs=evidence),),
                evidence_refs=evidence,
            )
            plan = VerificationPlan(
                "top", (VerificationTarget.COCOTB,), protocol_models=(protocol,), register_models=(register,)
            )
            write_plan_outputs(default_config(root), (plan,))
            loaded = read_stored_plans(root / ".dv-platform" / "plans" / "plans.sqlite")
            self.assertEqual(loaded[0].protocol_models, (protocol,))
            self.assertEqual(loaded[0].register_models, (register,))


if __name__ == "__main__":
    unittest.main()
