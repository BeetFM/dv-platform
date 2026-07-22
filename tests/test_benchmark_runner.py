import json
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from pypdf import PdfWriter

from dv_platform.enterprise.benchmark import run_benchmark


class BenchmarkRunnerTests(unittest.TestCase):
    def test_records_identity_fingerprints_and_metrics(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            rtl = root / "design.sv"
            xml = root / "design.xml"
            pdf = root / "spec.pdf"
            output = root / "result.json"
            rtl.write_text("module a; endmodule\nmodule b; endmodule\n", encoding="utf-8")
            xml.write_text("<root><module/><module/></root>", encoding="utf-8")
            writer = PdfWriter()
            writer.add_blank_page(width=72, height=72)
            with pdf.open("wb") as stream:
                writer.write(stream)
            with patch("dv_platform.enterprise.benchmark.detect_platform", return_value="wsl2-ubuntu-24.04"):
                result = run_benchmark(repo_root=Path.cwd(), rtl=rtl, xml=xml, pdf=pdf, output=output, profile="test")
            self.assertEqual(result["schema_version"], 2)
            self.assertEqual(result["inputs"]["rtl_lines"], 2)
            self.assertEqual(set(result["stages"]), {"rtl_scan", "xml_parse", "pdf_parse"})
            self.assertTrue({"python", "defusedxml", "pypdf"} <= set(result["tool_versions"]))
            self.assertEqual(json.loads(output.read_text(encoding="utf-8"))["profile"], "test")


if __name__ == "__main__":
    unittest.main()
