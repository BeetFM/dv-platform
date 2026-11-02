"""Complete, bounded native proofs of every Boolean output and next-state cone."""

from __future__ import annotations

import hashlib
import json
import shutil
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from time import monotonic

from dv_platform.enterprise.boolean_cones import cone_miter, is_defined_boolean, load_aag
from dv_platform.enterprise.equivalence import _verify_inputs
from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.physical_design import file_digest, tcl_string, write_document

_MIN_COMPARISONS = 1024


def needs_cones(models) -> bool:
    count = sum(len(port["bits"]) for port in models["gold"]["ports"].values() if port["direction"] == "output")
    return count >= _MIN_COMPARISONS


def supports_cones(models) -> bool:
    return needs_cones(models) and all(is_defined_boolean(model) for model in models.values())


def normalize_boolean_models(output, execute):
    execute(
        "cone-normalize",
        [
            "read_json cut-models.json",
            "techmap",
            "opt_clean",
            "check -assert",
            "select -assert-none a:blackbox",
            "write_json boolean-models.json",
        ],
        ("boolean-models.json",),
    )
    path = output / "boolean-models.json"
    if path.stat().st_size > 256 * 1024 * 1024:
        raise ValueError("Boolean models exceed their 256 MiB parsing bound")
    return json.loads(path.read_text())["modules"]


def _symbols(module, direction):
    return {
        name if len(port["bits"]) == 1 else f"{name}[{index}]"
        for name, port in module["ports"].items()
        if port["direction"] == direction
        for index in range(len(port["bits"]))
    }


def _prepare_aigs(models, output, execute):
    commands = ["read_json boolean-models.json", "design -save complete"]
    for label in ("gold", "gate"):
        commands += [
            "design -load complete",
            f"hierarchy -check -top {label}",
            "rename -enumerate -pattern gia_%",
            "aigmap",
            "opt_clean",
            "check -assert",
            f"write_aiger -ascii -symbols {label}.aag",
        ]
    execute("cone-prepare", commands, ("gold.aag", "gate.aag"))
    gold, gate = (load_aag(output / f"{label}.aag") for label in ("gold", "gate"))
    if gold["symbols"] != gate["symbols"]:
        raise ValueError("Boolean AIG interfaces do not preserve shared input/output bindings")
    for kind, direction in (("i", "input"), ("o", "output")):
        if set(gold["symbols"][kind].values()) != _symbols(models["gold"], direction):
            raise ValueError("Boolean AIG interface does not cover every original port bit")
    return gold, gate


def _inventory(gold, gate, output, deadline):
    directory = output / "cones"
    directory.mkdir()
    obligations, unique = [], {}
    for index, (left, right) in enumerate(zip(gold["outputs"], gate["outputs"], strict=True)):
        if monotonic() >= deadline:
            raise ValueError("complete cone proof exceeded its shared deadline")
        data, bindings = cone_miter(gold, gate, left, right)
        digest = hashlib.sha256(data).hexdigest()
        path = directory / f"{digest}.aag"
        if digest not in unique:
            path.write_bytes(data)
            unique[digest] = len(data)
        elif path.read_bytes() != data:
            raise ValueError("Boolean cone hash collision")
        obligations.append(
            {"index": index, "name": gold["symbols"]["o"][index], "miter_sha256": digest, "source_inputs": bindings}
        )
    write_document(output / "cone-inventory.json", {"obligations": obligations, "unique_cones": unique})
    return obligations, unique


def _prove_cone(path, directory, tools, deadline):
    directory.mkdir(parents=True, exist_ok=False)
    script = directory / "equivalence.ys"
    script.write_text(
        f"read_aiger -module_name miter {tcl_string(str(path.resolve()))}\n"
        "hierarchy -check -top miter\ncheck -assert\nselect -assert-none a:blackbox\n"
        f"abc -exe {tcl_string(str(tools['abc']))} -g AND\nopt_clean\ncheck -assert\n"
        "sat -verify -prove difference 0 -show-ports\nwrite_json equivalence.json\n"
    )
    hashes = {path: path.stem, script: file_digest(script), **{p: file_digest(p) for p in tools.values()}}
    _verify_inputs(hashes)
    remaining = min(300, deadline - monotonic())
    if remaining <= 0:
        raise ValueError("complete cone proof exceeded its shared deadline")
    receipt = run_native(
        (
            str(tools["limiter"]),
            f"--as={address_space_limit(256)}",
            "--core=0",
            "--",
            str(tools["yosys"]),
            "-Q",
            "-T",
            "-s",
            script.name,
        ),
        directory,
        "equivalence",
        timeout=remaining,
        expected=("equivalence.json",),
    )
    hashes.update({directory / name: digest for name, digest in receipt["artifacts"].items()})
    if json.loads((directory / "equivalence.receipt.json").read_text()) != receipt:
        raise ValueError("Boolean cone native receipt changed after execution")
    _verify_inputs(hashes)
    if "SAT proof finished - no model found: SUCCESS!" not in (directory / "equivalence.stdout.log").read_text():
        raise ValueError("Boolean cone has no native SAT success evidence")
    _verify_inputs(hashes)
    return {str(p): file_digest(p) for p in directory.iterdir() if p.is_file()}


def _proof_pool(output, unique, tools, deadline, workers):
    proved = {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {
            pool.submit(
                _prove_cone, output / "cones" / f"{digest}.aag", output / "cone-proofs" / digest, tools, deadline
            ): digest
            for digest in sorted(unique, key=unique.get)
        }
        try:
            for future in as_completed(futures):
                digest = futures[future]
                proved[digest] = future.result()
                write_document(
                    output / "cone-progress.json",
                    {"passed_unique_cones": len(proved), "required_unique_cones": len(unique), "complete": False},
                )
        except BaseException:
            for future in futures:
                future.cancel()
            raise
    return proved


def prove_cones(models, output, execute, deadline, memory_mb):
    """Discharge every comparison; reuse only identical miters within this run."""
    executables = {
        name: shutil.which(executable)
        for name, executable in (("yosys", "yosys"), ("abc", "yosys-abc"), ("limiter", "prlimit"))
    }
    if any(path is None for path in executables.values()):
        raise ValueError("Boolean cone proofs require Yosys, yosys-abc and prlimit")
    tools = {name: Path(path).resolve() for name, path in executables.items() if path is not None}
    limit = address_space_limit(memory_mb)
    if limit < 1536 * 1024 * 1024:
        raise ValueError("Boolean cone proof requires at least 1536 MiB of inherited address-space budget")
    workers = min(6, (limit // (1024 * 1024) - 1024) // 512)
    hashes = {
        p: file_digest(p)
        for p in [*tools.values(), output / "cut-models.json", output / "boolean-models.json", Path(__file__)]
    }
    gold, gate = _prepare_aigs(models, output, execute)
    hashes.update({output / f"{label}.aag": file_digest(output / f"{label}.aag") for label in ("gold", "gate")})
    obligations, unique = _inventory(gold, gate, output, deadline)
    hashes[output / "cone-inventory.json"] = file_digest(output / "cone-inventory.json")
    _verify_inputs(hashes)
    proofs = _proof_pool(output, unique, tools, deadline, workers)
    if set(proofs) != set(unique):
        raise ValueError("Boolean proof did not discharge every comparison")
    _verify_inputs(hashes)
    for artifacts in proofs.values():
        _verify_inputs({Path(path): digest for path, digest in artifacts.items()})
    if monotonic() >= deadline:
        raise ValueError("complete cone proof exceeded its shared deadline")
    result = {
        "status": "passed",
        "comparisons": len(obligations),
        "unique_cones": len(unique),
        "workers": workers,
        "per_native_memory_mib": 256,
        "method": "Exact Boolean cone miters, pinned ABC normalization and native SAT",
        "tool_sha256": {name: hashes[path] for name, path in tools.items()},
    }
    write_document(output / "equivalence.json", result)
    write_document(
        output / "cone-progress.json",
        {
            "passed_unique_cones": len(proofs),
            "required_unique_cones": len(unique),
            "complete": True,
        },
    )
    return result
