"""Immutable RTL/document snapshots and bounded, isolated source edits."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

from dv_platform.enterprise.native import address_space_limit, run_native
from dv_platform.enterprise.rtl_frontend import convert_sources, synthesis_source
from dv_platform.enterprise.transition_equivalence import prove_mapped_equivalence as prove_equivalence
from dv_platform.physical_design import _relative as normalized_path
from dv_platform.physical_design import tcl_string, write_document
from dv_platform.signoff import identity

MAX_SOURCE_BYTES = 4 * 1024 * 1024
MAX_CONTEXT_BYTES = 16 * 1024 * 1024


def _relative(name: str) -> Path:
    return Path(normalized_path(name))


def _read(root: Path, name: str) -> bytes:
    relative = _relative(name)
    target = root / relative
    if any((root / Path(*relative.parts[:index])).is_symlink() for index in range(1, len(relative.parts) + 1)):
        raise ValueError("RTL inputs must not contain symlinks")
    if not target.resolve().is_relative_to(root.resolve()) or not target.is_file():
        raise ValueError("RTL input is missing or outside the source root")
    with target.open("rb") as stream:
        data = stream.read(MAX_SOURCE_BYTES + 1)
    if len(data) > MAX_SOURCE_BYTES:
        raise ValueError("RTL input exceeds its size bound")
    data.decode("utf-8")
    return data


def snapshot_rtl(root: Path, sources: list[str], documents: list[str], output: Path) -> dict[str, Any]:
    """Freeze explicitly selected source and design-document bytes without modifying originals."""
    if not sources or not documents or len(sources) + len(documents) > 256:
        raise ValueError("RTL optimization needs bounded sources and design documents")
    names = sources + documents
    if len(set(names)) != len(names):
        raise ValueError("RTL inputs must be unique")
    if any(_relative(name).suffix not in {".v", ".sv", ".vh", ".svh"} for name in sources):
        raise ValueError("RTL sources must be Verilog or SystemVerilog")
    if any((root / _relative(name)).resolve().is_relative_to(output.resolve()) for name in names):
        raise ValueError("RTL snapshot must not contain an original input")
    contents = {name: _read(root, name) for name in names}
    if sum(map(len, contents.values())) > MAX_CONTEXT_BYTES:
        raise ValueError("RTL snapshot exceeds its total size bound")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in contents.items():
        target = output / "inputs" / _relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    record = {
        "schema_version": 1,
        "sources": sources,
        "documents": documents,
        "sha256": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
    }
    write_document(output / "snapshot.json", record)
    return record


def materialize_candidate(
    snapshot: Path, record: dict[str, Any], edits: list[dict[str, str]], output: Path
) -> dict[str, Any]:
    """Apply exact-text replacements only to hash-verified RTL in a fresh directory."""
    names = record["sources"] + record["documents"]
    if set(names) != set(record["sha256"]) or len(names) != len(set(names)):
        raise ValueError("RTL snapshot input set is inconsistent")
    contents = {name: _read(snapshot / "inputs", name) for name in names}
    if any(hashlib.sha256(data).hexdigest() != record["sha256"][name] for name, data in contents.items()):
        raise ValueError("RTL snapshot changed after capture")
    _apply_edits(contents, record.get("editable_sources", record["sources"]), edits)
    if sum(map(len, contents.values())) > MAX_CONTEXT_BYTES:
        raise ValueError("RTL candidate exceeds its total size bound")
    if output.resolve().is_relative_to(snapshot.resolve()):
        raise ValueError("RTL candidate must be outside the immutable snapshot")
    output.mkdir(parents=True, exist_ok=False)
    for name, data in contents.items():
        target = output / "inputs" / _relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
    result = {
        "status": "unverified",
        "signoff_approved": False,
        "baseline_sha256": record["sha256"],
        "candidate_sha256": {name: hashlib.sha256(data).hexdigest() for name, data in contents.items()},
        "edits": edits,
    }
    write_document(output / "candidate.json", result)
    return result


def _apply_edits(contents, sources, edits) -> None:
    if not isinstance(edits, list) or not 1 <= len(edits) <= 32:
        raise ValueError("RTL candidate requires 1..32 edits")
    for edit in edits:
        if (
            not isinstance(edit, dict)
            or set(edit) != {"path", "before", "after"}
            or any(not isinstance(value, str) for value in edit.values())
        ):
            raise ValueError("RTL edit has unknown or invalid fields")
        name, before, after = edit["path"], edit["before"], edit["after"]
        if name not in sources or not before or before == after:
            raise ValueError("RTL edit must change a declared source")
        text = contents[name].decode("utf-8")
        if text.count(before) != 1:
            raise ValueError("RTL edit must match exactly once")
        updated = text.replace(before, after, 1).encode("utf-8")
        forbidden = r"(?m)^.*(?:`include|\$readmem[hb]|translate_off|synthesis_off|blackbox|whitebox).*$"
        if re.findall(forbidden, updated.decode("utf-8")) != re.findall(forbidden, text):
            raise ValueError("RTL edit changes external-file or synthesis-control directives")
        if len(updated) > MAX_SOURCE_BYTES:
            raise ValueError("RTL candidate exceeds its size bound")
        contents[name] = updated


def prove_rtl_candidate(
    snapshot: Path,
    record: dict[str, Any],
    edits: list[dict[str, str]],
    design: str,
    output: Path,
    *,
    frontend: dict[str, Any] | None = None,
    memory_mb: int = 6144,
) -> dict[str, Any]:
    """Lower both source versions and require every sequential equivalence obligation."""
    identity(design)
    result = materialize_candidate(snapshot, record, edits, output)
    try:
        for label, root in (("reference", snapshot / "inputs"), ("candidate", output / "inputs")):
            lower_rtl_sources(root, record["sources"], design, output / label, frontend=frontend, memory_mb=memory_mb)
        proof = prove_equivalence(
            output / "reference/logical.v",
            output / "candidate/logical.v",
            [],
            design,
            output / "equivalence",
            ports_only=True,
            memory_mb=memory_mb,
        )
        result.update(status="equivalent", proof=proof)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        result.update(status="rejected", error=str(error))
    finally:
        write_document(output / "candidate.json", result)
    return result


def lower_rtl_sources(
    root: Path,
    sources: list[str],
    design: str,
    work: Path,
    *,
    frontend: dict[str, Any] | None = None,
    memory_mb: int = 6144,
) -> Path:
    """Lower declared sources with the same synthesis semantics for both versions."""
    identity(design)
    if type(memory_mb) is not int or not 256 <= memory_mb <= 262144:
        raise ValueError("RTL memory budget must be within 256..262144 MiB")
    executable, limiter = shutil.which("yosys"), shutil.which("prlimit")
    if executable is None or limiter is None:
        raise ValueError("RTL verification requires Yosys and prlimit")
    work.mkdir(parents=True, exist_ok=False)
    for name in sources:
        target = work / "inputs" / _relative(name)
        target.parent.mkdir(parents=True, exist_ok=True)
        data = _read(root, name)
        target.write_bytes(synthesis_source(data.decode("utf-8")).encode("utf-8") if frontend else data)
    includes = sorted({str(Path("inputs") / parent) for name in sources for parent in _relative(name).parents})
    flags = " ".join("-I" + tcl_string(name) for name in includes)
    files = " ".join(tcl_string("inputs/" + name) for name in sources if Path(name).suffix in {".v", ".sv"})
    if frontend is not None:
        convert_sources(work, sources, design, frontend, memory_mb=memory_mb)
        files = "converted.v"
    script = work / "synthesize.ys"
    script.write_text(
        f"read_verilog -sv {flags} {files}\n"
        f"hierarchy -check -top {design}\n"
        "proc\nmemory\nopt -keepdc\nflatten\ncheck -assert\n"
        "select -assert-none a:blackbox\nwrite_verilog -noattr logical.v\n"
    )
    run_native(
        (
            limiter,
            f"--as={address_space_limit(memory_mb)}",
            "--core=0",
            "--",
            executable,
            "-Q",
            "-T",
            "-s",
            script.name,
        ),
        work,
        "synthesize",
        expected=("logical.v",),
    )
    return work / "logical.v"
