import sys
from unittest import TestCase, skipUnless
from unittest.mock import patch

from dv_platform.enterprise.native import address_space_limit


@skipUnless(sys.platform.startswith("linux"), "native resource limits require Linux")
class InheritedLimitTests(TestCase):
    def test_requested_soft_and_hard_limits_are_all_respected(self):
        for requested, inherited, expected in (
            (6144, (-1, -1), 6144),
            (6144, (1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024), 1024),
            (6144, (-1, 2 * 1024 * 1024 * 1024), 2048),
            (512, (2 * 1024 * 1024 * 1024, 2 * 1024 * 1024 * 1024), 512),
        ):
            with (
                self.subTest(requested=requested, inherited=inherited),
                patch("resource.getrlimit", return_value=inherited),
            ):
                self.assertEqual(address_space_limit(requested), expected * 1024 * 1024)
