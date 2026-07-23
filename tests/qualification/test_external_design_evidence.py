import hashlib
import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.core.models import RTLModule, RTLParameter, RTLPort
from dv_platform.enterprise.external_design import (
    compare_surelog_structure,
    decode_surelog_uhdm_text,
    verify_external_design_evidence,
)


class ExternalDesignEvidenceTests(unittest.TestCase):
    def test_surelog_uhdm_structure_is_decoded_and_compared_fail_closed(self) -> None:
        text = r"""
noise
|uhdmallModules:
\_module_inst: work@demo (work@demo), file:demo.sv
  |vpiParameter:
  \_parameter: (work@demo.WIDTH), line:1:1
    |vpiName:WIDTH
  |vpiPort:
  \_port: (clk), line:2:1
    |vpiDirection:1
    |vpiLowConn:
      \_port: (nested_duplicate)
  |vpiPort:
  \_port: (data), line:3:1
    |vpiDirection:2
"""
        facts = decode_surelog_uhdm_text(text, "demo")
        self.assertEqual(facts.ports, (("clk", "input"), ("data", "output")))
        self.assertEqual(facts.parameters, ("WIDTH",))
        module = RTLModule(
            name="demo",
            port_details=(RTLPort("clk", "input"), RTLPort("data", "output")),
            parameter_details=(RTLParameter("WIDTH"),),
        )
        self.assertEqual(compare_surelog_structure(module, facts), ())
        mismatched = RTLModule(name="demo", port_details=(RTLPort("clk", "output"),))
        self.assertEqual(len(compare_surelog_structure(mismatched, facts)), 2)
        with self.assertRaisesRegex(ValueError, "top mismatch"):
            decode_surelog_uhdm_text(text, "other")

    def test_checked_in_records_verify_and_tampering_or_incomplete_frontends_fail(self) -> None:
        root = Path(__file__).resolve().parents[2]
        records = tuple(sorted((root / "qualification" / "external-designs").glob("*.json")))
        self.assertEqual(len(records), 2)
        for record in records:
            with self.subTest(record=record.name):
                self.assertEqual(verify_external_design_evidence(record)["status"], "passed")

        with TemporaryDirectory() as directory:
            payload = json.loads(records[0].read_text(encoding="utf-8"))
            payload["frontends"] = payload["frontends"][:-1]
            unsigned = dict(payload)
            unsigned.pop("evidence_sha256", None)
            payload["evidence_sha256"] = hashlib.sha256(
                json.dumps(unsigned, sort_keys=True, separators=(",", ":")).encode()
            ).hexdigest()
            path = Path(directory) / "incomplete.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "frontend set"):
                verify_external_design_evidence(path)

            payload = json.loads(records[0].read_text(encoding="utf-8"))
            payload["top"] = "tampered"
            path.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "digest mismatch"):
                verify_external_design_evidence(path)


if __name__ == "__main__":
    unittest.main()
