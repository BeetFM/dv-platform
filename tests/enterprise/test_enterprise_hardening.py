import json
import sys
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import MagicMock, patch

from dv_platform.enterprise.adapters import (
    EnterpriseAdapterError,
    EnterpriseCommandAdapter,
    OpenROADRunner,
    _load_result,
)
from dv_platform.enterprise.profiles import ENTERPRISE_TOOL_PROFILES, detect_enterprise_tools, enterprise_profile
from tests.enterprise.test_enterprise_adapters import _invocation


class EnterpriseAdapterHardeningTests(TestCase):
    def test_rejects_unsafe_invocation_contracts(self) -> None:
        class WrongKindRunner(EnterpriseCommandAdapter):
            profile_name = "openroad"

        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = _invocation(root, ("tool",))
            cases = (
                (OpenROADRunner(), replace(base, family="formal")),
                (WrongKindRunner(), base),
                (OpenROADRunner(), replace(base, command=())),
                (OpenROADRunner(), replace(base, command=("bad\x00arg",))),
                (OpenROADRunner(), replace(base, timeout_seconds=0)),
                (
                    OpenROADRunner(),
                    replace(
                        base,
                        environment_names=("TOKEN",),
                        environment=(("TOKEN", "one"), ("TOKEN", "two")),
                    ),
                ),
                (OpenROADRunner(), replace(base, environment=(("not-safe", "value"),))),
                (OpenROADRunner(), replace(base, environment=(("UNDECLARED", "value"),))),
                (OpenROADRunner(), replace(base, redact_patterns=("(",))),
            )
            for index, (runner, invocation) in enumerate(cases):
                with self.subTest(index=index), self.assertRaises(EnterpriseAdapterError):
                    runner.execute(invocation)

    def test_cancellation_reaps_the_native_process(self) -> None:
        with TemporaryDirectory() as directory:
            process = MagicMock()
            process.poll.return_value = None
            process.wait.side_effect = [KeyboardInterrupt, 0]
            with (
                patch("dv_platform.enterprise.adapters.subprocess.Popen", return_value=process),
                patch("dv_platform.enterprise.adapters.os.killpg") as kill,
            ):
                with self.assertRaises(KeyboardInterrupt):
                    OpenROADRunner().execute(_invocation(Path(directory), ("tool",)))
            kill.assert_called_once()
            self.assertEqual(process.wait.call_count, 2)

    def test_output_aliases_and_links_are_rejected_before_process_launch(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            base = _invocation(root, ("tool",))
            target = root / "target.json"
            target.write_text("preserved")
            link = root / "linked.json"
            link.symlink_to(target)
            for invocation in (replace(base, result_path=base.stdout_path), replace(base, result_path=link)):
                with (
                    self.subTest(invocation=invocation),
                    patch("dv_platform.enterprise.adapters.subprocess.Popen") as spawn,
                ):
                    with self.assertRaises(EnterpriseAdapterError):
                        OpenROADRunner().execute(invocation)
                    spawn.assert_not_called()
            self.assertEqual(target.read_text(), "preserved")

    def test_rejects_malformed_normalized_results(self) -> None:
        valid = {
            "schema_version": 1,
            "status": "passed",
            "checks": [
                {
                    "check_id": "CHK-1",
                    "module": "bridge",
                    "kind": "simulation",
                    "status": "passed",
                    "message": "complete",
                    "source_location": "bridge.sv:1",
                }
            ],
            "artifacts": [],
            "diagnostics": [],
        }
        cases: list[object] = [
            [],
            {**valid, "unexpected": True},
            {**valid, "schema_version": 99},
            {**valid, "status": "running"},
            {**valid, "checks": "invalid"},
            {**valid, "checks": [{**valid["checks"][0], "unexpected": True}]},
            {**valid, "checks": [valid["checks"][0], valid["checks"][0]]},
            {**valid, "checks": [{**valid["checks"][0], "status": "waived"}]},
            {**valid, "checks": [{**valid["checks"][0], "check_id": ""}]},
            {**valid, "checks": [{**valid["checks"][0], "message": 4}]},
            {**valid, "artifacts": [{"kind": "coverage", "path": "x", "extra": True}]},
            {**valid, "diagnostics": [7]},
        ]
        with TemporaryDirectory() as directory:
            root = Path(directory)
            result_path = root / "result.json"
            result_path.write_text("not-json", encoding="utf-8")
            with self.assertRaisesRegex(EnterpriseAdapterError, "invalid enterprise result JSON"):
                _load_result(result_path, root)
            for index, payload in enumerate(cases):
                result_path.write_text(json.dumps(payload), encoding="utf-8")
                with self.subTest(index=index), self.assertRaises(EnterpriseAdapterError):
                    _load_result(result_path, root)

            target = root / "target.json"
            target.write_text(json.dumps(valid), encoding="utf-8")
            link = root / "linked.json"
            link.symlink_to(target)
            with self.assertRaisesRegex(EnterpriseAdapterError, "escapes working directory"):
                _load_result(link, root)

    def test_normalizes_nonzero_strict_and_timeout_results(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)

            def command(result_path: Path, status: str = "passed", exit_code: int = 0) -> tuple[str, ...]:
                script = (
                    "import json,pathlib,sys; "
                    "pathlib.Path(sys.argv[1]).write_text(json.dumps({"
                    "'schema_version':1,'status':'passed',"
                    f"'checks':[{{'check_id':'CHK','module':'bridge','kind':'property','status':'{status}'}}],"
                    "'artifacts':[],'diagnostics':['vendor diagnostic']}),encoding='utf-8'); "
                    f"raise SystemExit({exit_code})"
                )
                return (sys.executable, "-c", script, str(result_path))

            result_path = root / "nonzero.json"
            nonzero = OpenROADRunner().execute(
                replace(_invocation(root, command(result_path, exit_code=3)), result_path=result_path)
            )
            self.assertEqual(nonzero.status, "failed")
            self.assertIn("non-zero", " ".join(nonzero.diagnostics))

            result_path = root / "strict.json"
            strict = OpenROADRunner().execute(
                replace(_invocation(root, command(result_path, status="skipped")), result_path=result_path),
                strict=True,
            )
            self.assertEqual(strict.status, "failed")
            self.assertIn("skipped", " ".join(strict.diagnostics))

            timeout = OpenROADRunner().execute(
                replace(
                    _invocation(root, (sys.executable, "-c", "import time; time.sleep(2)")),
                    result_path=root / "timeout.json",
                    timeout_seconds=0.01,
                )
            )
            self.assertEqual(timeout.status, "timeout")
            self.assertIsNone(timeout.return_code)


class EnterpriseProfileAndCLIHardeningTests(TestCase):
    def test_profile_lookup_and_detection_are_fail_closed(self) -> None:
        with self.assertRaisesRegex(LookupError, "unknown enterprise tool profile"):
            enterprise_profile("missing")
        with (
            patch("dv_platform.enterprise.profiles.which", side_effect=lambda command: f"/eda/{command}"),
            patch.dict("os.environ", {}, clear=True),
        ):
            detected = detect_enterprise_tools()
        self.assertEqual(len(detected), len(ENTERPRISE_TOOL_PROFILES))
        self.assertTrue(all(item.available for item in detected))
