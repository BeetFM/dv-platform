import unittest
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.configuration import validate_config
from dv_platform.core.config import default_config
from dv_platform.core.models import RTLMemory, RTLModule, VerificationDepthPolicy
from dv_platform.verification.memory_init import bind_memory_initializations, validate_memory_initialization


class MemoryInitializationTests(unittest.TestCase):
    def test_valid_image_is_strict_and_digest_bound(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "rtl" / "init.hex"
            image.parent.mkdir()
            image.write_text("00\n01\nfe\nff\n", encoding="ascii")
            result = validate_memory_initialization(
                root,
                "rtl/init.hex",
                depth=4,
                width=8,
                memory="ram",
                default_policy="file_complete",
            )
        self.assertEqual(result.words, (0, 1, 254, 255))
        self.assertRegex(result.sha256, r"^[0-9a-f]{64}$")

    def test_rejects_escape_symlink_unknown_depth_width_and_overflow(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            image = root / "init.hex"
            image.write_text("00\nxz\n", encoding="ascii")
            link = root / "link.hex"
            link.symlink_to(image)
            cases = (
                ("../init.hex", 2, 8, "file_complete"),
                ("link.hex", 2, 8, "file_complete"),
                ("init.hex", 3, 8, "file_complete"),
                ("init.hex", 2, 4, "file_complete"),
                ("init.hex", 2, 8, "implicit"),
            )
            for path, depth, width, policy in cases:
                with self.subTest(path=path, depth=depth, width=width, policy=policy):
                    with self.assertRaises(ValueError):
                        validate_memory_initialization(
                            root,
                            path,
                            depth=depth,
                            width=width,
                            memory="ram",
                            default_policy=policy,
                        )

    def test_binding_attaches_identity_and_rejects_stale_configured_digest(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "init.hex").write_text("00\n01\n", encoding="ascii")
            module = RTLModule(
                name="top",
                source=Path("rtl/top.sv"),
                memories=(RTLMemory("ram", element_width=8, depth=2, address_width=1),),
            )
            parameters = (
                ("profile", "bounded_sram_init_hex"),
                ("path", "init.hex"),
                ("default_policy", "file_complete"),
            )
            policy = VerificationDepthPolicy("memory", "top", "ram", parameters)
            bound = bind_memory_initializations(root, (module,), (policy,))
            memory = bound[0].memories[0]
            self.assertEqual(memory.initialization_path, "init.hex")
            self.assertRegex(memory.initialization_sha256 or "", r"^[0-9a-f]{64}$")

            stale = VerificationDepthPolicy("memory", "top", "ram", (*parameters, ("sha256", "0" * 64)))
            with self.assertRaisesRegex(ValueError, "digest is stale"):
                bind_memory_initializations(root, (module,), (stale,))

    def test_public_configuration_rejects_incomplete_or_unsafe_hex_profiles(self) -> None:
        base = VerificationDepthPolicy(
            "memory",
            "top",
            "ram",
            (
                ("profile", "bounded_sram_init_hex"),
                ("path", "rtl/init.hex"),
                ("default_policy", "file_complete"),
            ),
        )
        config = replace(default_config(Path.cwd()), depth_policies=(base,))
        self.assertFalse([item for item in validate_config(config) if item.severity == "error"])
        for parameters in (
            (("profile", "bounded_sram_init_hex"),),
            (("profile", "bounded_sram_init_hex"), ("path", "../init.hex"), ("default_policy", "file_complete")),
            (
                ("profile", "bounded_sram_init_hex"),
                ("path", "rtl/init.hex"),
                ("default_policy", "implicit"),
            ),
            (("profile", "bounded_sram"), ("path", "rtl/init.hex")),
        ):
            with self.subTest(parameters=parameters):
                invalid = replace(config, depth_policies=(VerificationDepthPolicy("memory", "top", "ram", parameters),))
                self.assertTrue([item for item in validate_config(invalid) if item.severity == "error"])


if __name__ == "__main__":
    unittest.main()
