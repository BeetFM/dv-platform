import json
import os
import stat
import sys
import zipfile
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from dv_platform.core.config import default_config, write_config
from dv_platform.core.models import AdapterPluginConfig
from dv_platform.enterprise.qualification import (
    QualificationError,
    create_vendor_qualification_bundle,
    import_vendor_attestation,
    qualification_status,
    qualify_contract,
    qualify_surrogate,
    set_qualification_policy,
)
from dv_platform.qualification_assets import vendor_runner
from tests.test_enterprise_cli import _main


class EnterpriseQualificationTests(TestCase):
    def test_contract_records_and_policy_are_enforced(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                adapter_plugins=(AdapterPluginConfig("simulator_runner", "questa"),),
            )
            record = qualify_contract(config, "questa")
            self.assertEqual(record["level"], "contract_verified")

            set_qualification_policy(config, "contract_verified", max_age_days=365)
            self.assertTrue(qualification_status(config)["passed"])

            set_qualification_policy(config, "vendor_verified", profile="questa")
            status = qualification_status(config)
            self.assertFalse(status["passed"])
            self.assertEqual(status["failures"][0]["code"], "enterprise_qualification_below_policy")

            record_path = Path(status["records"][0]["path"])
            invalid_record = dict(record)
            invalid_record["tools"] = []
            record_path.write_text(json.dumps(invalid_record), encoding="utf-8")
            policy_path = Path(status["policy_path"])
            policy_path.write_text("{", encoding="utf-8")
            corrupt_codes = {item["code"] for item in qualification_status(config)["failures"]}
            self.assertIn("qualification_policy_invalid", corrupt_codes)
            self.assertIn("qualification_record_invalid", corrupt_codes)

    def test_open_source_surrogate_probe_records_actual_version(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            executable = root / "verilator"
            executable.write_text(
                '#!/bin/sh\nif [ "$1" = "--version" ]; then echo \'Verilator qualification-fake 1\'; fi\nexit 0\n',
                encoding="utf-8",
            )
            executable.chmod(executable.stat().st_mode | stat.S_IXUSR)
            config = replace(
                default_config(root),
                adapter_plugins=(AdapterPluginConfig("analyzer_runner", "spyglass"),),
            )
            with patch.dict(os.environ, {"PATH": str(root)}, clear=False):
                record = qualify_surrogate(config, "spyglass", probe_names=("verilator_lint",))

            self.assertEqual(record["level"], "surrogate_verified")
            self.assertEqual(record["families"], ["analyzer"])
            self.assertIn("qualification-fake", record["tools"][0]["version"])

    def test_vendor_bundle_executes_and_imports_tamper_evident_attestation(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "questa-qualification.zip"
            metadata = create_vendor_qualification_bundle("questa", bundle)
            self.assertEqual(metadata["profile"], "questa")
            extracted = root / "bundle"
            with zipfile.ZipFile(bundle) as archive:
                archive.extractall(extracted)
            wrapper = extracted / "wrapper.py"
            wrapper.write_text(
                "import json,os,pathlib\n"
                "pathlib.Path(os.environ['DV_PLATFORM_RESULT_PATH']).write_text(json.dumps({"
                "'schema_version':1,'status':'passed',"
                "'checks':[{'check_id':'SITE-PREFLIGHT','module':'dv_qualification',"
                "'kind':'simulation','status':'passed'},"
                "{'check_id':'QUAL-SIM-001','module':'dv_qualification',"
                "'kind':'simulation','status':'passed'}],'artifacts':[],'diagnostics':[]}),encoding='utf-8')\n",
                encoding="utf-8",
            )
            with patch.object(
                sys,
                "argv",
                [
                    "run_qualification.py",
                    "--request",
                    str(extracted / "qualification-request.json"),
                    "--tool-name",
                    "Questa",
                    "--tool-version",
                    "2026.1",
                    "--",
                    sys.executable,
                    str(wrapper),
                ],
            ):
                self.assertEqual(vendor_runner.main(), 0)
            config = replace(
                default_config(root),
                adapter_plugins=(AdapterPluginConfig("simulator_runner", "questa"),),
            )
            attestation = extracted / "qualification-attestation.json"
            record = import_vendor_attestation(config, "questa", attestation)
            self.assertEqual(record["level"], "vendor_verified")
            self.assertEqual(record["tools"][0]["version"], "2026.1")
            self.assertEqual(record["checks"][0]["check_id"], "QUAL-SIM-001")

            payload = json.loads(attestation.read_text(encoding="utf-8"))
            payload["tool"]["version"] = "tampered"
            attestation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(QualificationError, "integrity check failed"):
                import_vendor_attestation(config, "questa", attestation)

    def test_cli_exposes_fixture_bundle_and_policy_workflows(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                adapter_plugins=(AdapterPluginConfig("simulator_runner", "questa"),),
            )
            config_path = root / "dv-platform.toml"
            write_config(config, config_path)
            common = ["--repo-root", str(root), "--config", str(config_path), "--json"]
            status, payload = _main(common + ["qualify", "--profile", "questa", "--mode", "fixture"])
            self.assertEqual(status, 0, payload)
            self.assertEqual(payload["data"]["level"], "contract_verified")

            status, payload = _main(
                common
                + [
                    "qualification-policy",
                    "--minimum-level",
                    "contract_verified",
                    "--max-age-days",
                    "30",
                ]
            )
            self.assertEqual(status, 0, payload)

            status, payload = _main(
                common
                + [
                    "qualification-bundle",
                    "--profile",
                    "questa",
                    "--output",
                    str(root / "qualification.zip"),
                ]
            )
            self.assertEqual(status, 0, payload)
            self.assertTrue((root / "qualification.zip").is_file())
