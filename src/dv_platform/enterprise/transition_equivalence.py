"""Complete combinational transition checks for matched, uninitialized register states."""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from time import monotonic
from typing import Any

from dv_platform.enterprise import boolean_cones, cone_equivalence
from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.physical_design import file_digest, tcl_string, write_document
from dv_platform.signoff import identity


class UnsupportedStateCorrespondence(ValueError):
    """The transition method cannot establish a complete supported state relation."""


def prove_mapped_equivalence(
    reference: Path,
    candidate: Path,
    libraries: list[Path],
    design: str,
    output: Path,
    *,
    timeout: float = 3600,
    memory_mb: int = 6144,
    ports_only: bool = False,
) -> dict[str, Any]:
    """Use complete transitions where supported, otherwise retain clock-event proof."""
    from dv_platform.enterprise.equivalence import prove_equivalence

    deadline = monotonic() + timeout
    try:
        return prove_transition_equivalence(
            reference, candidate, libraries, design, output, timeout=timeout, memory_mb=memory_mb
        )
    except UnsupportedStateCorrespondence as error:
        write_document(output / "transition-unsupported.json", {"reason": str(error)})
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError("equivalence exceeded its shared deadline") from error
        result = prove_equivalence(
            reference,
            candidate,
            libraries,
            design,
            output / "clock-events",
            timeout=remaining,
            memory_mb=memory_mb,
            ports_only=ports_only,
        )
        result["transition_fallback_reason"] = str(error)
        result["artifacts"] = {str(p.relative_to(output)): file_digest(p) for p in output.rglob("*") if p.is_file()}
        write_document(output / "proof.json", result)
        return result


def prove_transition_equivalence(
    reference: Path,
    candidate: Path,
    libraries: list[Path],
    design: str,
    output: Path,
    *,
    timeout: float = 3600,
    memory_mb: int = 6144,
) -> dict[str, Any]:
    """Prove every output and D cone under a complete, clock-checked state bijection.

    Unsupported state correspondence, initialized state, derived clocks, or clock
    polarities fail closed. This check does not prove a changed state encoding.
    """
    from dv_platform.enterprise.equivalence import _verify_inputs

    identity(design)
    if type(memory_mb) is not int or not 256 <= memory_mb <= 262144 or not 0 < timeout <= 86400:
        raise ValueError("invalid transition-equivalence resource budget")
    executable, limiter = shutil.which("yosys"), shutil.which("prlimit")
    if executable is None or limiter is None:
        raise ValueError("transition equivalence requires Yosys and prlimit")
    limit = address_space_limit(memory_mb)
    output.mkdir(parents=True, exist_ok=False)
    hashes = _proof_inputs(reference, candidate, libraries)
    deadline = monotonic() + timeout

    def execute(name, commands, expected):
        _verify_inputs(hashes)
        script = output / f"{name}.ys"
        script.write_text("\n".join(commands) + "\n")
        hashes[script] = file_digest(script)
        remaining = deadline - monotonic()
        if remaining <= 0:
            raise ValueError("transition equivalence exceeded its shared deadline")
        receipt = run_native(
            (limiter, f"--as={limit}", "--core=0", "--", executable, "-Q", "-T", "-s", script.name),
            output,
            name,
            timeout=remaining,
            expected=expected,
        )
        hashes.update({output / name: receipt["artifacts"][name] for name in expected})
        _verify_inputs(hashes)

    models, excluded = _prepare_models(reference, candidate, libraries, design, output, hashes, execute)
    _verify_inputs(hashes)
    outputs = sum(len(p["bits"]) for p in models["gold"]["ports"].values() if p["direction"] == "output")
    pairs, clock = _expose_states(models)
    if outputs == 0:
        raise ValueError("transition proof requires observable outputs")
    model = output / "cut-models.json"
    write_document(model, {"modules": models})
    hashes[model] = file_digest(model)
    _prove_transitions(models, output, execute, deadline, memory_mb)
    _verify_inputs(hashes)
    result = {
        "status": "passed",
        "method": "Complete clock-checked state correspondence and ABC/SAT transition proof",
        "comparison_scope": "every primary output and every matched register D cone for all shared input/state assignments",
        "normalization": "Native Yosys opt -full with standard synthesis don't-care semantics",
        "proven_output_bits": outputs,
        "proven_next_state_bits": len(pairs),
        "clock": clock,
        "state_correspondence": pairs,
        "reference_sha256": hashes[reference],
        "candidate_sha256": hashes[candidate],
        "libraries_sha256": {str(p): hashes[p] for p in libraries},
        "excluded_disconnected_physical_cells": excluded,
        "artifacts": {str(p.relative_to(output)): file_digest(p) for p in output.rglob("*") if p.is_file()},
        "checker_sha256": hashes[Path(__file__)],
        "checker_sources_sha256": {
            str(path): hashes[path]
            for path in (Path(__file__), Path(boolean_cones.__file__), Path(cone_equivalence.__file__))
        },
    }
    write_document(output / "proof.json", result)
    return result


def _proof_inputs(reference, candidate, libraries):
    paths = (
        reference,
        candidate,
        *libraries,
        Path(__file__),
        Path(boolean_cones.__file__),
        Path(cone_equivalence.__file__),
    )
    return {path: file_digest(path) for path in paths}


def _prove_transitions(models, output, execute, deadline, memory_mb):
    if cone_equivalence.needs_cones(models):
        normalized = cone_equivalence.normalize_boolean_models(output, execute)
        if cone_equivalence.supports_cones(normalized):
            cone_equivalence.prove_cones(normalized, output, execute, deadline, memory_mb)
            return
    execute("equivalence", _proof_commands(), ("equivalence.json",))


def _prepare_models(reference, candidate, libraries, design, output, hashes, execute):
    from dv_platform.enterprise.equivalence import _logical_netlist

    models, excluded = {}, {}
    for label, original in (("gold", reference), ("gate", candidate)):
        normalized = output / f"{label}.v"
        excluded[label] = _logical_netlist(original, normalized)
        hashes[normalized] = file_digest(normalized)
        execute(
            f"prepare-{label}",
            [
                *[f"read_liberty -ignore_miss_func {tcl_string(str(path.resolve()))}" for path in libraries],
                f"read_verilog -sv {tcl_string(str(normalized.resolve()))}",
                f"hierarchy -check -top {design}",
                "proc",
                "memory",
                "setattr -mod -unset keep_hierarchy",
                "setattr -unset keep_hierarchy",
                "flatten -wb",
                "opt -full",
                "dffunmap",
                "simplemap",
                "opt -full",
                "dffunmap",
                "simplemap",
                "opt_clean",
                "check -assert",
                "select -assert-none a:blackbox",
                f"rename {design} {label}",
                f"write_json {label}.json",
            ],
            (f"{label}.json",),
        )
        path = output / f"{label}.json"
        if path.stat().st_size > 128 * 1024 * 1024:
            raise UnsupportedStateCorrespondence("transition model exceeds its 128 MiB parsing bound")
        models[label] = json.loads(path.read_text())["modules"][label]
    return models, excluded


def _registers(module):
    if any("init" in n.get("attributes", {}) for n in module["netnames"].values()):
        raise UnsupportedStateCorrespondence("transition correspondence does not support initialized registers")
    registers = {}
    inputs = {
        bit: (name, index)
        for name, p in module["ports"].items()
        if p["direction"] == "input"
        for index, bit in enumerate(p["bits"])
    }
    for name, cell in module["cells"].items():
        if "ff" not in cell["type"].lower():
            continue
        if cell["type"] != "$_DFF_P_" or cell["connections"]["C"][0] not in inputs:
            raise UnsupportedStateCorrespondence("transition correspondence requires rising-edge primary-input clocks")
        q = cell["connections"]["Q"][0]
        if q in registers:
            raise ValueError("transition state has multiple register drivers")
        registers[q] = (name, cell["connections"]["D"], inputs[cell["connections"]["C"][0]])
    return registers


def _expose_states(models):
    gold, gate = models["gold"], models["gate"]

    def interface(module):
        return {
            n: {k: v for k, v in p.items() if k != "bits"} | {"width": len(p["bits"])}
            for n, p in module["ports"].items()
        }

    if interface(gold) != interface(gate):
        raise ValueError("transition interfaces differ")
    registers = {label: _registers(module) for label, module in models.items()}
    pairs = _state_pairs(gold, gate, registers)
    clocks = {registers[label][q][2] for qgold, qgate in pairs for label, q in (("gold", qgold), ("gate", qgate))}
    if len(clocks) > 1:
        raise UnsupportedStateCorrespondence("transition correspondence requires one identical primary clock")
    for index, (qgold, qgate) in enumerate(pairs):
        for label, q in (("gold", qgold), ("gate", qgate)):
            module = models[label]
            name, d, _ = registers[label][q]
            for suffix, direction, bits in (("q", "input", [q]), ("d", "output", d)):
                port = f"transition_state_{index}_{suffix}"
                if port in module["ports"] or port in module["netnames"]:
                    raise ValueError("transition proof port collides with a design signal")
                module["ports"][port] = {"direction": direction, "bits": bits}
                module["netnames"][port] = {"hide_name": 0, "bits": bits, "attributes": {}}
            del module["cells"][name]
    return pairs, next(iter(clocks)) if clocks else None


def _state_pairs(gold, gate, registers):
    import re

    lookup = {
        (n, i): b
        for n, net in gate["netnames"].items()
        if not net["hide_name"]
        for i, b in enumerate(net["bits"])
        if b in registers["gate"]
    }
    candidates: dict[int, set[int]] = {q: set() for q in registers["gold"]}
    named_candidates: dict[int, set[int]] = {q: set() for q in registers["gold"]}
    for name, net in gold["netnames"].items():
        if not net["hide_name"]:
            for index, bit in enumerate(net["bits"]):
                if bit in candidates and (name, index) in lookup:
                    candidates[bit].add(lookup[name, index])
                    # Lowered Verilog exposes recycled Yosys _NN_ names as public nets.
                    if not re.search(r"\$|(?:^|\.)_\d+_(?:\.|$)", name):
                        named_candidates[bit].add(lookup[name, index])
    candidates = {q: named_candidates[q] or values for q, values in candidates.items()}
    if any(len(values) != 1 for values in candidates.values()):
        raise UnsupportedStateCorrespondence("transition register correspondence is missing or ambiguous")
    pairs = [(q, next(iter(values))) for q, values in sorted(candidates.items())]
    if len(pairs) != len({gate for _, gate in pairs}) or len(pairs) != len(registers["gate"]):
        raise UnsupportedStateCorrespondence("transition register correspondence is not complete and bijective")
    return pairs


def _proof_commands():
    return [
        "read_json cut-models.json",
        "miter -equiv -flatten -make_assert gold gate miter",
        "hierarchy -check -top miter",
        "check -assert",
        "techmap",
        "opt",
        "abc -g AND",
        "opt_clean",
        "sat -enable_undef -set-def-inputs -verify -prove-asserts -show-ports",
        "write_json equivalence.json",
    ]
