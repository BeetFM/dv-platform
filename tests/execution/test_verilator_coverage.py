import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.coverage import import_coverage_reports
from dv_platform.core.config import default_config
from dv_platform.execution.coverage.verilator import (
    MAX_COUNTER,
    VerilatorCoverageDatImporter,
    VerilatorCoverageImportError,
)


def _record(*, count: int, name: str = "branch taken", excluded: str = "0") -> str:
    metadata = (
        "\x01f\x02rtl/top.sv\x01l\x0212\x01h\x02top.u_core"
        f"\x01s\x02WIDTH=8\x01t\x02branch\x01o\x02{name}\x01x\x02{excluded}"
    )
    return f"C '{metadata}' {count}\n"


class VerilatorCoverageDatImporterTests(unittest.TestCase):
    def test_import_is_canonical_and_merges_duplicate_counters(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.dat"
            path.write_text(_record(count=2) + _record(count=3), encoding="utf-8")

            first = VerilatorCoverageDatImporter().import_coverage(path)
            second = VerilatorCoverageDatImporter().import_coverage(path)

        self.assertEqual(first, second)
        point = first["coverage_points"][0]
        self.assertEqual(point["hits"], 5)
        self.assertEqual(point["status"], "covered")
        self.assertRegex(point["point_id"], r"^verilator:[0-9a-f]{64}$")
        self.assertEqual(point["vendor_provenance"]["record_lines"], "1,2")

    def test_importer_flows_through_normal_closure_policy(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "coverage.dat"
            path.write_text(_record(count=0), encoding="utf-8")

            _summary_path, summary = import_coverage_reports(
                default_config(root),
                (path,),
                coverage_importers=(VerilatorCoverageDatImporter(),),
            )

        self.assertFalse(summary["passed"])
        self.assertEqual(summary["closure"]["counts"]["uncovered"], 1)
        self.assertRegex(summary["closure"]["points"][0]["point_id"], r"^verilator:[0-9a-f]{64}$")

    def test_exclusion_and_counter_overflow_are_preserved(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.coverage.dat"
            path.write_text(_record(count=MAX_COUNTER + 7, excluded="yes"), encoding="utf-8")

            point = VerilatorCoverageDatImporter().import_coverage(path)["coverage_points"][0]

        self.assertEqual(point["hits"], MAX_COUNTER)
        self.assertEqual(point["status"], "excluded")
        self.assertEqual(point["vendor_provenance"]["counter_overflow"], "true")

    def test_rejects_malformed_or_unbounded_records(self) -> None:
        with TemporaryDirectory() as directory:
            path = Path(directory) / "coverage.dat"
            for content in ("C 'not-tagged' 1\n", "C '\\x01f\\x02rtl/top.sv' 1\n", "bad\n"):
                path.write_text(content, encoding="utf-8")
                with self.subTest(content=content), self.assertRaises(VerilatorCoverageImportError):
                    VerilatorCoverageDatImporter().import_coverage(path)


if __name__ == "__main__":
    unittest.main()
