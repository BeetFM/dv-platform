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
from dv_platform.qualification_assets import vendor_runner, vivado_xsim_runner
from tests.test_enterprise_cli import _main


class EnterpriseQualificationTests(TestCase):
    def test_checked_in_vivado_xsim_attestation_matches_generated_uvm(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            config = replace(
                default_config(root),
                adapter_plugins=(AdapterPluginConfig("simulator_runner", "vivado_xsim"),),
            )
            attestation = (
                Path(__file__).resolve().parents[1]
                / "docs"
                / "evidence"
                / "vivado-xsim-2025.2-qualification-attestation.json"
            )

            record = import_vendor_attestation(config, "vivado_xsim", attestation)

            self.assertEqual(record["level"], "vendor_verified")
            self.assertEqual(record["tools"][0]["version"], "2025.2")
            self.assertEqual(
                {item["check_id"] for item in record["checks"]},
                {"QUAL-SIM-001", "QUAL-UVM-001"},
            )
            set_qualification_policy(config, "vendor_verified", profile="vivado_xsim")
            self.assertTrue(qualification_status(config)["passed"])

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
            metadata = create_vendor_qualification_bundle("questa", bundle, include_generated_uvm=True)
            self.assertEqual(metadata["profile"], "questa")
            extracted = root / "bundle"
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("fixtures/generated_uvm/uvm_stream_loopback_pkg.sv", archive.namelist())
                self.assertIn("fixtures/generated_uvm/tb_uvm_stream_loopback_uvm.sv", archive.namelist())
                archive.extractall(extracted)
            wrapper = extracted / "wrapper.py"
            wrapper.write_text(
                "import json,os,pathlib\n"
                "pathlib.Path(os.environ['DV_PLATFORM_RESULT_PATH']).write_text(json.dumps({"
                "'schema_version':1,'status':'passed',"
                "'checks':[{'check_id':'SITE-PREFLIGHT','module':'dv_qualification',"
                "'kind':'simulation','status':'passed'},"
                "{'check_id':'QUAL-SIM-001','module':'dv_qualification',"
                "'kind':'simulation','status':'passed'},"
                "{'check_id':'QUAL-UVM-001','module':'uvm_stream_loopback',"
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
            self.assertEqual(record["checks"][1]["check_id"], "QUAL-UVM-001")

            payload = json.loads(attestation.read_text(encoding="utf-8"))
            payload["tool"]["version"] = "tampered"
            attestation.write_text(json.dumps(payload), encoding="utf-8")
            with self.assertRaisesRegex(QualificationError, "integrity check failed"):
                import_vendor_attestation(config, "questa", attestation)

    def test_vivado_xsim_bundle_and_wrapper_require_non_vacuous_uvm_markers(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            bundle = root / "vivado-xsim-qualification.zip"
            create_vendor_qualification_bundle("vivado_xsim", bundle, include_generated_uvm=True)
            with zipfile.ZipFile(bundle) as archive:
                self.assertIn("run_vivado_xsim.py", archive.namelist())

            result_path = root / "enterprise-result.json"
            environment = {
                "DV_PLATFORM_QUALIFICATION_ROOT": str(root),
                "DV_PLATFORM_RESULT_PATH": str(result_path),
            }
            tools = {name: root / name for name in ("xvlog", "xelab", "xsim")}
            simulator_output = "dv-platform qualification passed"
            uvm_output = "\n".join(
                (
                    "Running test uvm_stream_loopback_test...",
                    "[TEST_DONE] run phase complete",
                    "UVM_ERROR : 0",
                    "UVM_FATAL : 0",
                )
            )
            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(vivado_xsim_runner, "_resolve_tools", return_value=tools),
                patch.object(
                    vivado_xsim_runner,
                    "_run_pipeline",
                    side_effect=(
                        vivado_xsim_runner.CommandResult(0, simulator_output),
                        vivado_xsim_runner.CommandResult(0, uvm_output),
                    ),
                ),
            ):
                self.assertEqual(vivado_xsim_runner.main(["--vivado-bin", str(root)]), 0)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "passed")
            self.assertEqual({item["check_id"] for item in payload["checks"]}, {"QUAL-SIM-001", "QUAL-UVM-001"})

            with (
                patch.dict(os.environ, environment, clear=False),
                patch.object(vivado_xsim_runner, "_resolve_tools", return_value=tools),
                patch.object(
                    vivado_xsim_runner,
                    "_run_pipeline",
                    side_effect=(
                        vivado_xsim_runner.CommandResult(0, simulator_output),
                        vivado_xsim_runner.CommandResult(0, "UVM test exited without a report summary"),
                    ),
                ),
            ):
                self.assertEqual(vivado_xsim_runner.main(["--vivado-bin", str(root)]), 1)
            payload = json.loads(result_path.read_text(encoding="utf-8"))
            self.assertEqual(payload["status"], "failed")
            self.assertEqual(payload["checks"][1]["status"], "failed")

    def test_vivado_xsim_wrapper_process_and_resolution_boundaries(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            native_bin = root / "native"
            windows_bin = root / "windows"
            native_bin.mkdir()
            windows_bin.mkdir()
            for name in ("xvlog", "xelab", "xsim"):
                (native_bin / name).write_text("tool", encoding="utf-8")
                (windows_bin / f"{name}.bat").write_text("tool", encoding="utf-8")

            native_tools = vivado_xsim_runner._resolve_tools(native_bin, windows=False)
            windows_tools = vivado_xsim_runner._resolve_tools(windows_bin, windows=True)
            self.assertEqual(native_tools["xsim"], native_bin / "xsim")
            self.assertEqual(windows_tools["xsim"], windows_bin / "xsim.bat")
            with self.assertRaisesRegex(SystemExit, "does not exist"):
                vivado_xsim_runner._resolve_tools(root / "missing", windows=False)
            empty = root / "empty"
            empty.mkdir()
            with self.assertRaisesRegex(SystemExit, "unavailable"):
                vivado_xsim_runner._resolve_tools(empty, windows=False)

            with patch.object(
                vivado_xsim_runner,
                "_run_tool",
                side_effect=(
                    vivado_xsim_runner.CommandResult(0, "compile"),
                    vivado_xsim_runner.CommandResult(0, "elaborate"),
                    vivado_xsim_runner.CommandResult(0, "simulate"),
                ),
            ) as run_tool:
                pipeline = vivado_xsim_runner._run_pipeline(
                    native_tools,
                    root,
                    ("source.sv",),
                    "top",
                    "snapshot",
                    None,
                    10,
                    uvm=True,
                )
            self.assertEqual(pipeline.return_code, 0)
            self.assertEqual(run_tool.call_count, 3)
            self.assertIn("-L", run_tool.call_args_list[0].args[1])

            with patch.object(
                vivado_xsim_runner,
                "_run_tool",
                return_value=vivado_xsim_runner.CommandResult(7, "compile failed"),
            ) as run_tool:
                pipeline = vivado_xsim_runner._run_pipeline(
                    native_tools,
                    root,
                    ("source.sv",),
                    "top",
                    "snapshot",
                    None,
                    10,
                    uvm=False,
                )
            self.assertEqual(pipeline.return_code, 7)
            run_tool.assert_called_once()

            native = vivado_xsim_runner._run_tool(
                Path(sys.executable),
                ("-c", "print('native-ok')"),
                root,
                None,
                10,
            )
            self.assertEqual(native.return_code, 0)
            self.assertIn("native-ok", native.output)

            batch = windows_bin / "xvlog.bat"
            cmd_exe = root / "cmd.exe"
            cmd_exe.write_text("tool", encoding="utf-8")
            with self.assertRaisesRegex(SystemExit, "--cmd-exe"):
                vivado_xsim_runner._run_tool(batch, (), root, None, 10)
            with (
                patch.object(vivado_xsim_runner, "_windows_path", return_value=r"C:\Vivado\xvlog.bat"),
                patch.object(vivado_xsim_runner.subprocess, "run") as run,
            ):
                run.return_value.returncode = 0
                run.return_value.stdout = "windows-ok"
                run.return_value.stderr = ""
                windows = vivado_xsim_runner._run_tool(batch, ("-sv", "source.sv"), root, cmd_exe, 10)
            self.assertEqual(windows.return_code, 0)
            self.assertIn("windows-ok", windows.output)

            with patch.object(vivado_xsim_runner.subprocess, "run", side_effect=OSError("denied")):
                failed = vivado_xsim_runner._run_tool(Path(sys.executable), (), root, None, 10)
            self.assertEqual(failed.return_code, 124)

            with patch.object(vivado_xsim_runner.subprocess, "run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "C:\\translated\n"
                self.assertEqual(vivado_xsim_runner._windows_path(root), r"C:\translated")
                run.return_value.returncode = 1
                with self.assertRaisesRegex(SystemExit, "cannot translate"):
                    vivado_xsim_runner._windows_path(root)

            with self.assertRaisesRegex(SystemExit, "1..3600"):
                vivado_xsim_runner.main(["--vivado-bin", str(root), "--timeout-seconds", "0"])
            with patch.dict(os.environ, {}, clear=True), self.assertRaisesRegex(SystemExit, "is required"):
                vivado_xsim_runner._environment_path("DV_PLATFORM_RESULT_PATH")

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
