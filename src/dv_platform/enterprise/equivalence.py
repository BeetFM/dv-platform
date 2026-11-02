"""Yosys sequential equivalence without fixture-specific state assumptions."""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path
from time import monotonic as _monotonic
from typing import Any

from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.physical_design import file_digest, tcl_string, write_document
from dv_platform.signoff import identity


def prove_equivalence(
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
    identity(design)
    executable = shutil.which("yosys")
    limiter = shutil.which("prlimit")
    if executable is None or limiter is None:
        raise ValueError("equivalence requires Yosys and prlimit")
    if not 256 <= memory_mb <= 262144:
        raise ValueError("equivalence memory budget must be within 256..262144 MiB")
    if not 0 < timeout <= 86400:
        raise ValueError("equivalence timeout must be within 0..86400 seconds")
    limit = address_space_limit(memory_mb)
    output.mkdir(parents=True, exist_ok=False)
    gold, gate = reference.resolve(), candidate.resolve()
    hashes = {path: file_digest(path) for path in [gold, gate, *libraries]}
    normalized = []
    stages: list[tuple[str, list[str], tuple[str, ...]]] = []
    deadline = _monotonic() + timeout
    for label, original in (("gold", gold), ("gate", gate)):
        path = output / f"{label}.v"
        normalized.append(_logical_netlist(original, path))
        hashes[path] = file_digest(path)
        stages.append(
            (f"prepare-{label}", _model_commands(path, libraries, design, label, ports_only), (f"{label}.il",))
        )
        stages.append((f"validate-{label}", _validation_commands(label), ()))
    stages.append(("equivalence", _proof_commands(ports_only), ("equivalence.json",)))
    for name, commands, expected in stages:
        _verify_inputs(hashes)
        script = output / f"{name}.ys"
        script.write_text("\n".join(commands) + "\n")
        hashes[script] = file_digest(script)
        remaining = deadline - _monotonic()
        if remaining <= 0:
            raise subprocess.TimeoutExpired(executable, timeout)
        receipt = run_native(
            (limiter, f"--as={limit}", "--core=0", "--", executable, "-Q", "-T", "-s", script.name),
            output,
            name,
            timeout=remaining,
            expected=expected,
        )
        hashes.update({output / name: receipt["artifacts"][name] for name in expected if name.endswith(".il")})
    _verify_inputs(hashes)
    result = {
        "status": "passed",
        "comparison_scope": "ports" if ports_only else "matched_ports_and_internal_signals",
        "reference_sha256": hashes[gold],
        "candidate_sha256": hashes[gate],
        "libraries_sha256": {str(path): hashes[path] for path in libraries},
        "prepared_models_sha256": {name: hashes[output / name] for name in ("gold.il", "gate.il")},
        "normalized_inputs_sha256": {name: hashes[output / name] for name in ("gold.v", "gate.v")},
        "method": "Yosys staged clock-event lowering, equiv_simple and sequential induction; every equivalence obligation must be proven",
        "excluded_disconnected_physical_cells": normalized,
        "artifacts": {path.name: file_digest(path) for path in output.iterdir() if path.is_file()},
    }
    write_document(output / "proof.json", result)
    return result


def _verify_inputs(hashes) -> None:
    if any(file_digest(path) != digest for path, digest in hashes.items()):
        raise ValueError("equivalence inputs changed during execution")


def _model_commands(netlist, libraries, design, label, ports_only) -> list[str]:
    return [
        *[f"read_liberty -ignore_miss_func {tcl_string(str(path.resolve()))}" for path in libraries],
        f"read_verilog -sv {tcl_string(str(netlist))}",
        f"hierarchy -check -top {design}",
        "proc",
        "memory",
        "opt -keepdc",
        # Keep clock-model optimization within modules to bound memory before flattening.
        "clk2fflogic",
        "opt -keepdc",
        "setattr -mod -unset keep_hierarchy",
        "setattr -unset keep_hierarchy",
        "flatten -wb",
        "opt_clean",
        *(["rename -hide w:* c:*"] if ports_only else []),
        f"rename {design} {label}",
        f"write_rtlil {label}.il",
    ]


def _validation_commands(label) -> list[str]:
    return [f"read_rtlil {label}.il", "check -assert", "select -assert-none a:blackbox"]


def _proof_commands(ports_only) -> list[str]:
    return [
        "read_rtlil gold.il",
        "read_rtlil gate.il",
        "equiv_make gold gate equiv" if ports_only else "equiv_make -inames gold gate equiv",
        "hierarchy -check -top equiv",
        "select -assert-min 1 t:$equiv",
        "equiv_simple -seq 8",
        "equiv_induct -seq 8",
        "equiv_status -assert",
        "write_json equivalence.json",
    ]


def _logical_netlist(source: Path, target: Path) -> dict[str, int]:
    if source.stat().st_size > 256 * 1024 * 1024:
        raise RuntimeError("logical netlist normalization exceeds its 256 MiB input bound")
    physical = re.compile(
        r"(?m)^[ \t]*(sky130_fd_sc_hd__(?:tapvpwrvgnd_1|decap_(?:3|4|6|8)|fill_(?:1|2|4|8)))"
        r"\s+(?:\\\S+|[A-Za-z_$][\w$]*)\s*\(([^;]{0,65536})\)\s*;[ \t]*$"
    )
    excluded: dict[str, int] = {}

    def remove(match: re.Match[str]) -> str:
        if match.group(2).strip():
            raise ValueError("physical-only cell has unexpected logical connections")
        name = match.group(1)
        excluded[name] = excluded.get(name, 0) + 1
        return ""

    target.write_text(physical.sub(remove, source.read_text()))
    return excluded
