"""Exact cone extraction preserves shared inputs, constants and every output bit."""

from copy import deepcopy
from itertools import product
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase

from dv_platform.enterprise.boolean_cones import cone_miter, is_defined_boolean, load_aag


def evaluate(model, output, inputs):
    values = [False, *inputs]
    for a, b in model["nodes"].values():
        values.append((values[a // 2] ^ bool(a & 1)) and (values[b // 2] ^ bool(b & 1)))
    return values[output // 2] ^ bool(output & 1)


def boolean_module():
    return {
        "ports": {
            "a": {"direction": "input", "bits": [2]},
            "b": {"direction": "input", "bits": [3]},
            "q": {"direction": "output", "bits": [4]},
        },
        "cells": {
            "gate": {
                "type": "$_AND_",
                "connections": {"A": [2], "B": [3], "Y": [4]},
                "port_directions": {"A": "input", "B": "input", "Y": "output"},
            }
        },
    }


class BooleanConeTests(TestCase):
    def setUp(self):
        temporary = TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_all_small_truth_tables_preserve_the_source_input_bijection(self):
        gold = {"inputs": 3, "nodes": {4: (2, 4), 5: (9, 6)}}
        gate = {"inputs": 3, "nodes": {4: (4, 6), 5: (3, 8)}}
        for left, right in product(range(12), repeat=2):
            data, bindings = cone_miter(gold, gate, left, right)
            path = self.root / "miter.aag"
            path.write_bytes(data)
            miter = load_aag(path)
            for assignment in product((False, True), repeat=3):
                local = [assignment[var - 1] for var in bindings]
                self.assertEqual(
                    evaluate(miter, miter["outputs"][0], local),
                    evaluate(gold, left, assignment) ^ evaluate(gate, right, assignment),
                )

    def test_deep_cones_do_not_use_python_recursion(self):
        gold = {"inputs": 2, "nodes": {var: (2 * (var - 1) + 1, 2) for var in range(3, 2003)}}
        gold["nodes"][3] = (4, 2)
        data, bindings = cone_miter(gold, gold, 4004, 4005)
        path = self.root / "deep.aag"
        path.write_bytes(data)
        miter = load_aag(path)
        self.assertEqual(bindings, [])
        self.assertEqual(miter["outputs"], [1])

    def test_local_isomorphic_cones_reuse_only_a_complete_miter(self):
        gold = {"inputs": 3, "nodes": {4: (2, 4), 5: (4, 6)}}
        gate = {"inputs": 3, "nodes": {4: (3, 4), 5: (5, 6)}}
        first, binding1 = cone_miter(gold, gate, 8, 8)
        second, binding2 = cone_miter(gold, gate, 10, 10)
        self.assertEqual(first, second)
        self.assertNotEqual(binding1, binding2)
        self.assertNotEqual(first, cone_miter(gold, gate, 8, 9)[0])

    def test_boolean_eligibility_excludes_undef_cycles_and_driver_ambiguity(self):
        module = boolean_module()
        self.assertTrue(is_defined_boolean(module))
        for port, bits in (
            ("A", ["x"]),
            ("A", ["z"]),
            ("A", [99]),
            ("A", [4]),
            ("A", [2, 3]),
            ("Y", [2]),
            ("Y", ["0"]),
        ):
            candidate = deepcopy(module)
            candidate["cells"]["gate"]["connections"][port] = bits
            with self.subTest(port=port, bits=bits):
                self.assertFalse(is_defined_boolean(candidate))
        for mutate in (
            lambda m: m["cells"]["gate"].update(type="$_DFF_P_"),
            lambda m: m["cells"].update(other=deepcopy(m["cells"]["gate"])),
            lambda m: m["ports"]["q"].update(bits=["x"]),
            lambda m: m["ports"]["a"].update(bits=["0"]),
            lambda m: m["ports"]["a"].update(bits=[3]),
            lambda m: m["cells"]["gate"]["port_directions"].update(A="output"),
        ):
            candidate = deepcopy(module)
            mutate(candidate)
            self.assertFalse(is_defined_boolean(candidate))

    def test_aig_parser_rejects_incomplete_or_ambiguous_interfaces(self):
        valid = "aag 3 2 0 1 1\n2\n4\n6\n6 2 4\ni0 a\ni1 b\no0 q\nc\n"
        for bad in (
            valid.replace("aag", "aig"),
            valid.replace("3 2 0", "3 2 1"),
            valid.replace("3 2 0 1 1", "4 2 0 1 1"),
            valid.replace("2\n4\n", "4\n2\n"),
            valid.replace("6 2 4", "6 2 6"),
            valid.replace("6 2 4\n", ""),
            valid.replace("i1 b", "i1 a"),
            valid.replace("i1 b", "i0 b"),
            valid.replace("i1 b\n", ""),
            valid.replace("o0 q", "o0 "),
            valid.replace("o0 q", "l0 q"),
            valid.replace("4\n6\n", "4\n8\n"),
        ):
            path = self.root / "invalid.aag"
            path.write_text(bad)
            with self.subTest(bad=bad), self.assertRaises(ValueError):
                load_aag(path)
