import json
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.cli import main
from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import AdapterPluginConfig


class ClosureAcceptanceTests(TestCase):
    def test_ucis_import_fails_unmapped_and_passes_mapped_points(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config_path = root / "dv-platform.toml"
            write_config(
                replace(
                    default_config(root),
                    adapter_plugins=(
                        AdapterPluginConfig(
                            kind="coverage_importer",
                            name="ucis_xml",
                        ),
                    ),
                ),
                config_path,
            )
            unmapped = root / "unmapped.ucis.xml"
            mapped = root / "mapped.ucis.xml"
            unmapped.write_text(_ucis_bin(), encoding="utf-8")
            mapped.write_text(_ucis_bin(' dvRequirementId="REQ-BRIDGE-1"'), encoding="utf-8")

            first_output = StringIO()
            with redirect_stdout(first_output):
                first_status = main(
                    [
                        "--repo-root",
                        str(root),
                        "--config",
                        str(config_path),
                        "--json",
                        "coverage",
                        "--input",
                        str(unmapped),
                        "--as-of",
                        "2026-07-19",
                    ]
                )
            first = json.loads(first_output.getvalue())

            self.assertEqual(first_status, 1)
            self.assertFalse(first["ok"])
            self.assertEqual(first["error"]["code"], "coverage_gate_failed")
            self.assertFalse(first["data"]["closure"]["traceability_complete"])

            second_output = StringIO()
            with redirect_stdout(second_output):
                second_status = main(
                    [
                        "--repo-root",
                        str(root),
                        "--config",
                        str(config_path),
                        "--json",
                        "coverage",
                        "--input",
                        str(mapped),
                        "--as-of",
                        "2026-07-19",
                    ]
                )
            second = json.loads(second_output.getvalue())

            self.assertEqual(second_status, 0)
            self.assertTrue(second["ok"])
            self.assertTrue(second["data"]["closure"]["traceability_complete"])
            exports = second["data"]["exports"]
            self.assertEqual(set(exports), {"json", "markdown", "sarif", "yaml"})
            self.assertTrue(all(Path(path).is_file() for path in exports.values()))


def _ucis_bin(attributes: str = "") -> str:
    return f"""\
<UCIS module="bridge"><covergroupCoverage><cgInstance name="cg">
  <coverpoint name="cp"><coverpointBin name="seen" type="bins"{attributes}
    coverageCount="1" /></coverpoint>
</cgInstance></covergroupCoverage></UCIS>
"""
