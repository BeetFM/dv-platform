import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis.parameters import expand_parameter_matrix
from dv_platform.core.config import load_config, write_config


class ParameterMatrixTests(unittest.TestCase):
    def test_cartesian_expansion_is_sorted_constrained_and_bounded(self) -> None:
        points = expand_parameter_matrix(
            (("WIDTH", ("8", "16")), ("DEPTH", ("2", "4"))),
            constraints=("WIDTH >= DEPTH", "DEPTH != 4 or WIDTH == 16"),
            maximum_points=4,
        )
        self.assertEqual(
            points,
            (("DEPTH=2", "WIDTH=8"), ("DEPTH=2", "WIDTH=16"), ("DEPTH=4", "WIDTH=16")),
        )
        with self.assertRaisesRegex(ValueError, "maximum_points"):
            expand_parameter_matrix((("A", ("1", "2")), ("B", ("1", "2"))), maximum_points=2)
        with self.assertRaisesRegex(ValueError, "unsupported"):
            expand_parameter_matrix((("A", ("1",)),), constraints=("__import__('os')",))

    def test_configuration_expands_matrix_into_isolated_sweeps(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "dv-platform.toml"
            path.write_text(
                """
[paths]
repo_root = "."
[rtl]
parameter_constraints = ["WIDTH >= DEPTH"]
max_parameter_points = 4
[rtl.parameter_matrix]
WIDTH = ["8", "16"]
DEPTH = ["4", "32"]
""",
                encoding="utf-8",
            )
            config = load_config(path)
            self.assertEqual(config.parameter_sweeps, (("DEPTH=4", "WIDTH=8"), ("DEPTH=4", "WIDTH=16")))
            self.assertEqual(config.parameter_matrix[0][0], "DEPTH")
            roundtrip = root / "roundtrip.toml"
            write_config(config, roundtrip)
            reloaded = load_config(roundtrip)
            self.assertEqual(reloaded.parameter_sweeps, config.parameter_sweeps)
            self.assertEqual(reloaded.parameter_matrix, config.parameter_matrix)


if __name__ == "__main__":
    unittest.main()
