from importlib.metadata import EntryPoint
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.analysis.ucis import UCISImportError, UCISXMLCoverageImporter
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.core.plugins import load_adapter_plugins


class UCISXMLCoverageImporterTests(TestCase):
    def test_loads_through_the_production_adapter_contract(self) -> None:
        entry_point = EntryPoint(
            name="ucis_xml",
            value="dv_platform.analysis.ucis:UCISXMLCoverageImporter",
            group="dv_platform.coverage_importer",
        )

        plugins = load_adapter_plugins(
            (AdapterPluginConfig(kind="coverage_importer", name="ucis_xml"),),
            entry_points=(entry_point,),
        )

        self.assertEqual(len(plugins), 1)
        self.assertEqual(plugins[0].kind, "coverage_importer")
        self.assertIsInstance(plugins[0].adapter, UCISXMLCoverageImporter)

    def test_imports_coverpoint_cross_ignore_and_illegal_bins(self) -> None:
        document = """\
<ucis:UCIS xmlns:ucis="urn:accellera:ucis">
  <ucis:covergroupCoverage>
    <ucis:cgInstance name="traffic">
      <ucis:coverpoint name="opcode">
        <ucis:options at_least="2" />
        <ucis:coverpointBin name="read" type="bins" dvCheckId="cp:read"
            dvRequirementId="REQ-1, REQ-2" dvBehaviorId="BEH-1">
          <ucis:range><ucis:contents coverageCount="2" /></ucis:range>
        </ucis:coverpointBin>
        <ucis:coverpointBin name="write" type="bins">
          <ucis:range><ucis:contents coverageCount="1" /></ucis:range>
        </ucis:coverpointBin>
        <ucis:coverpointBin name="reserved" type="ignore">
          <ucis:range><ucis:contents coverageCount="0" /></ucis:range>
        </ucis:coverpointBin>
        <ucis:coverpointBin name="bad" type="illegal">
          <ucis:range><ucis:contents coverageCount="1" /></ucis:range>
        </ucis:coverpointBin>
      </ucis:coverpoint>
      <ucis:cross name="opcode_x_ready">
        <ucis:crossBin name="read_ready">
          <ucis:contents coverageCount="3" />
        </ucis:crossBin>
      </ucis:cross>
    </ucis:cgInstance>
  </ucis:covergroupCoverage>
</ucis:UCIS>
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "run.ucis.xml"
            path.write_text(document, encoding="utf-8")
            importer = UCISXMLCoverageImporter()

            result = importer.import_coverage(path)

        self.assertTrue(importer.supports(path))
        self.assertEqual(result["schema_version"], 2)
        self.assertEqual(result["source_format"], "ucis-xml")
        self.assertEqual(result["formal_points"], [])
        points = result["coverage_points"]
        self.assertEqual(
            [point["status"] for point in points],
            ["covered", "uncovered", "excluded", "failed", "covered"],
        )
        self.assertEqual(points[0]["check_id"], "cp:read")
        self.assertEqual(points[0]["requirement_ids"], ["REQ-1", "REQ-2"])
        self.assertEqual(points[0]["behavior_ids"], ["BEH-1"])
        self.assertEqual(points[0]["module"], "run")
        self.assertEqual(points[0]["hits"], 2)
        self.assertEqual(points[-1]["kind"], "cross")
        self.assertEqual(len({point["id"] for point in points}), 5)

    def test_rejects_non_ucis_empty_and_unsafe_xml(self) -> None:
        importer = UCISXMLCoverageImporter()
        documents = (
            "<coverage />",
            "<UCIS />",
            '<!DOCTYPE UCIS [<!ENTITY x "bad">]><UCIS>&x;</UCIS>',
        )
        with TemporaryDirectory() as directory:
            for index, document in enumerate(documents):
                path = Path(directory) / f"invalid-{index}.ucis"
                path.write_text(document, encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(UCISImportError):
                    importer.import_coverage(path)

    def test_rejects_ambiguous_bin_data(self) -> None:
        document = """\
<UCIS><covergroupCoverage><cgInstance name="cg"><coverpoint name="cp">
  <coverpointBin name="unknown" type="vendor-special" coverageCount="1" />
</coverpoint></cgInstance></covergroupCoverage></UCIS>
"""
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ambiguous.ucis.xml"
            path.write_text(document, encoding="utf-8")
            with self.assertRaisesRegex(UCISImportError, "unsupported UCIS bin type"):
                UCISXMLCoverageImporter().import_coverage(path)
