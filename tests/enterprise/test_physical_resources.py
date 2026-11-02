import sys
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.enterprise.physical_design import _bounded_openroad_command


@skipUnless(sys.platform.startswith("linux"), "native resource limits require Linux prlimit")
class PhysicalResourceTests(TestCase):
    def test_native_command_preserves_stricter_inherited_budgets(self):
        for inherited, expected in (
            ((-1, -1), 4294967296),
            ((1073741824, 2147483648), 1073741824),
            ((2147483648, 2147483648), 2147483648),
        ):
            with (
                self.subTest(inherited=inherited),
                patch("resource.getrlimit", return_value=inherited),
                patch("dv_platform.enterprise.physical_design._executable", return_value="/tools/prlimit"),
            ):
                self.assertEqual(
                    _bounded_openroad_command("/tools/openroad"),
                    (
                        "/tools/prlimit",
                        f"--as={expected}",
                        "--core=0",
                        "--",
                        "/tools/openroad",
                        "-no_init",
                        "-exit",
                        "-metrics",
                        "pd-metrics.json",
                        "pd-driver.tcl",
                    ),
                )

    def test_missing_limiter_never_falls_back_to_uncapped_execution(self):
        with (
            patch("dv_platform.enterprise.physical_design.shutil.which", return_value=None),
            self.assertRaisesRegex(ValueError, "requires the prlimit executable"),
        ):
            _bounded_openroad_command("/tools/openroad")
