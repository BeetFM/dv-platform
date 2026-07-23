import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.agent.protocols import RegisterModel
from dv_platform.analysis.registers import (
    extract_registers_from_documentation,
    load_register_map,
    merge_register_sources,
)
from dv_platform.core.models import DocumentationChunk, RTLModule


class RegisterAnalysisTests(unittest.TestCase):
    def test_documentation_and_explicit_configuration_extract_fields(self) -> None:
        chunk = DocumentationChunk(
            "chunk-1",
            Path("spec.md"),
            "top register CONTROL @ 0x00 width=32 reset=0x1\n"
            "field ENABLE [0:0] access=rw reset=0\n"
            "field STATUS [7:4] access=ro reset=0x2 side_effect=clear_on_read\n",
        )
        documented = extract_registers_from_documentation((chunk,), "top")
        self.assertEqual(documented[0].offset, 0)
        self.assertEqual(documented[0].fields[1].side_effect, "clear_on_read")
        with TemporaryDirectory() as directory:
            path = Path(directory) / "registers.json"
            path.write_text(
                json.dumps({"module": "top", "registers": [{"name": "CONTROL", "offset": "0x0", "fields": []}]})
            )
            configured = load_register_map(path, "top")
            self.assertEqual(configured[0].source, "configuration")
            self.assertEqual(configured[0].evidence_refs[0].source_id, str(path))

    def test_conflicting_offsets_are_recorded_and_not_selected(self) -> None:
        first = RegisterModel("CONTROL", 0, 32, source="rtl")
        second = RegisterModel("CONTROL", 4, 32, source="documentation")
        result = merge_register_sources(RTLModule("top"), (("rtl", (first,)), ("docs", (second,))))
        self.assertEqual(result.registers, ())
        self.assertEqual(result.conflicts[0].property_name, "offset")
        self.assertIn("conflicting offset", result.open_questions[0])


if __name__ == "__main__":
    unittest.main()
