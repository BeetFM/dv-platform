"""The production cone backend retains state/clock/undef checks and native rejection."""

import json
import shutil
from pathlib import Path
from tempfile import TemporaryDirectory
from time import monotonic, sleep
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.enterprise import boolean_cones, transition_equivalence
from dv_platform.enterprise import cone_equivalence as cones
from dv_platform.enterprise.transition_equivalence import prove_transition_equivalence
from dv_platform.physical_design import file_digest
from dv_platform.signoff import verify_artifacts
from tests.enterprise import test_transition_equivalence as transition_tests
from tests.enterprise.test_boolean_cones import boolean_module


@skipUnless(shutil.which("yosys-abc"), "requires native ABC")
class NativeConeEquivalenceTests(transition_tests.TransitionEquivalenceTests):
    def setUp(self):
        super().setUp()
        threshold = patch.object(cones, "_MIN_COMPARISONS", 1)
        threshold.start()
        self.addCleanup(threshold.stop)

    def test_complete_native_inventory_and_every_artifact_are_retained(self):
        result = self.prove(transition_tests.RTL, "inventory")
        output = self.root / "inventory"
        inventory = json.loads((output / "cone-inventory.json").read_text())
        obligations = inventory["obligations"]
        self.assertEqual(len(obligations), 8)
        self.assertEqual([item["index"] for item in obligations], list(range(8)))
        self.assertEqual(len({item["name"] for item in obligations}), 8)
        summary = json.loads((output / "equivalence.json").read_text())
        self.assertEqual(summary["comparisons"], 8)
        self.assertEqual(set(summary["tool_sha256"]), {"yosys", "abc", "limiter"})
        sources = (Path(transition_equivalence.__file__), Path(cones.__file__), Path(boolean_cones.__file__))
        self.assertEqual(result["checker_sources_sha256"], {str(path): file_digest(path) for path in sources})
        self.assertTrue(any(name.startswith("cone-proofs/") for name in result["artifacts"]))
        verify_artifacts(output, result["artifacts"])
        target = next((output / "cone-proofs").glob("*/equivalence.json"))
        target.write_text("{}")
        with self.assertRaises(ValueError):
            verify_artifacts(output, result["artifacts"])

    def test_each_output_position_mutation_is_rejected_without_fallback(self):
        for bit in (0, 2, 3):
            source = transition_tests.RTL.replace("q=count", f"q=count ^ 4'd{1 << bit}")
            with self.subTest(bit=bit), self.assertRaisesRegex(ValueError, "native equivalence failed"):
                self.prove(source, f"wrong-{bit}")

    def test_undefined_output_retains_the_original_undef_aware_backend(self):
        source = "module block(input d,output [1:0] q); assign q={1'bx,d}; endmodule"
        self.gold.write_text(source)
        self.gate.write_text(source)
        result = prove_transition_equivalence(self.gold, self.gate, [], "block", self.root / "undef", timeout=30)
        self.assertEqual(result["status"], "passed")
        self.assertFalse((self.root / "undef/cone-inventory.json").exists())
        self.assertIn("-enable_undef", (self.root / "undef/equivalence.ys").read_text())

    def test_modified_native_cone_output_cannot_be_accepted(self):
        native = cones.run_native

        def tamper(command, directory, name, **kwargs):
            receipt = native(command, directory, name, **kwargs)
            (directory / "equivalence.json").write_text("{}")
            return receipt

        with patch.object(cones, "run_native", side_effect=tamper):
            with self.assertRaisesRegex(ValueError, "inputs changed"):
                self.prove(transition_tests.RTL, "tamper-cone")
        self.assertFalse((self.root / "tamper-cone/proof.json").exists())


class ConeResourceTests(TestCase):
    def test_unknown_models_and_small_models_never_select_boolean_proof(self):
        models = {"gold": boolean_module(), "gate": boolean_module()}
        self.assertFalse(cones.supports_cones(models))
        with patch.object(cones, "_MIN_COMPARISONS", 1):
            self.assertTrue(cones.supports_cones(models))
            models["gate"]["cells"]["gate"]["connections"]["A"] = ["x"]
            self.assertFalse(cones.supports_cones(models))

    def test_pool_failure_waits_for_started_workers_and_cancels_pending_proofs(self):
        active = set()

        def prove(path, directory, tools, deadline):
            active.add(path.stem)
            try:
                if path.stem == "0":
                    raise ValueError("invalid native proof")
                sleep(0.03)
                return {}
            finally:
                active.remove(path.stem)

        with patch.object(cones, "_prove_cone", side_effect=prove):
            with self.assertRaisesRegex(ValueError, "invalid native proof"):
                cones._proof_pool(Path("unused"), {str(i): i for i in range(30)}, {}, monotonic() + 10, 2)
        self.assertFalse(active)

    def test_missing_tools_and_insufficient_inherited_budget_fail_closed(self):
        with TemporaryDirectory() as temporary:
            output = Path(temporary)
            with patch.object(cones.shutil, "which", return_value=None):
                with self.assertRaisesRegex(ValueError, "require Yosys"):
                    cones.prove_cones({}, output, None, monotonic() + 10, 4096)
            with patch.object(cones.shutil, "which", return_value="/usr/bin/true"):
                with patch.object(cones, "address_space_limit", return_value=1024 * 1024 * 1024):
                    with self.assertRaisesRegex(ValueError, "inherited address-space"):
                        cones.prove_cones({}, output, None, monotonic() + 10, 4096)
            self.assertFalse((output / "equivalence.json").exists())
