import os
import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.core.config import default_config, validate_config
from dv_platform.core.sandbox import sandbox_command


class SandboxTests(unittest.TestCase):
    def test_rootless_command_denies_network_and_forwards_only_named_environment(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory).resolve()
            config = replace(
                default_config(root),
                sandbox_enabled=True,
                sandbox_runtime="podman",
                sandbox_image="registry.example/veriforge@sha256:" + "a" * 64,
                sandbox_environment=("LICENSE_FILE",),
                max_process_memory_mb=512,
            )
            with (
                patch("dv_platform.core.sandbox.shutil.which", return_value="/usr/bin/podman"),
                patch.dict(os.environ, {"LICENSE_FILE": "27000@server", "SECRET_NOT_ALLOWED": "no"}, clear=True),
            ):
                output = root / ".dv-platform" / "runs" / "one"
                command = sandbox_command(
                    config,
                    (str(root / "runner"), "input.sv"),
                    root,
                    writable_paths=(output,),
                )
            self.assertIn("--network=none", command)
            self.assertIn("--read-only", command)
            self.assertIn("--userns=keep-id", command)
            self.assertIn("--memory=512m", command)
            self.assertIn("LICENSE_FILE", command)
            self.assertNotIn("SECRET_NOT_ALLOWED", command)
            self.assertIn(str(root / "runner"), command)
            self.assertIn(f"{root}:{root}:ro,rprivate", command)
            self.assertIn(f"{output}:{output}:rw,rprivate", command)

    def test_sandbox_refuses_a_run_without_isolated_writable_output(self) -> None:
        config = replace(
            default_config(Path.cwd()),
            sandbox_enabled=True,
            sandbox_runtime="podman",
            sandbox_image="image@sha256:" + "a" * 64,
        )
        with patch("dv_platform.core.sandbox.shutil.which", return_value="/usr/bin/podman"):
            with self.assertRaisesRegex(ValueError, "isolated writable output"):
                sandbox_command(config, ("tool",), Path.cwd())

    def test_invalid_enabled_sandbox_and_license_budget_fail_configuration(self) -> None:
        config = replace(default_config(Path.cwd()), sandbox_enabled=True, license_tokens=0)
        messages = [item.message for item in validate_config(config)]
        self.assertTrue(any("license_tokens" in message for message in messages))
        self.assertTrue(any("sandbox execution" in message for message in messages))


if __name__ == "__main__":
    unittest.main()
