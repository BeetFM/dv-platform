"""Deterministic source discovery for local RTL repositories."""

from __future__ import annotations

import json
import shlex
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dv_platform.core.config import ConfigDiagnostic, normalize_path
from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, HDLFile
from dv_platform.core.paths import is_within

HDL_EXTENSIONS = {
    ".v": "verilog",
    ".vh": "verilog",
    ".sv": "systemverilog",
    ".svh": "systemverilog",
    ".vhd": "vhdl",
    ".vhdl": "vhdl",
}
DOCUMENTATION_EXTENSIONS = {".md", ".markdown", ".txt", ".rst", ".pdf"}
SKIPPED_DIRECTORIES = {
    ".git",
    ".hg",
    ".svn",
    ".dv-platform",
    ".mypy_cache",
    ".pytest_cache",
    ".ruff_cache",
    ".venv",
    "__pycache__",
    "build",
    "dist",
}


@dataclass(frozen=True)
class ProjectInventory:
    """Files and options discovered for one repository analysis pass."""

    hdl_files: tuple[HDLFile, ...]
    documentation_files: tuple[Path, ...]
    include_paths: tuple[Path, ...]
    defines: tuple[str, ...]


def discover_project(config: CLIConfig) -> ProjectInventory:
    """Discover HDL and documentation inputs from config."""

    filelist_sources: list[Path] = []
    filelist_include_paths: list[Path] = []
    filelist_defines: list[str] = []

    for filelist in config.rtl_filelists:
        parsed = parse_filelist(filelist, config.repo_root)
        filelist_sources.extend(hdl_file.path for hdl_file in parsed.hdl_files)
        filelist_include_paths.extend(parsed.include_paths)
        filelist_defines.extend(parsed.defines)

    if filelist_sources:
        hdl_files = tuple(_hdl_file(path) for path in _dedupe_paths(filelist_sources))
    else:
        excluded_roots = tuple(
            dict.fromkeys(
                (
                    config.work_dir,
                    config.output_dir,
                    config.retrieval_index_dir or config.work_dir / "rag-index",
                )
            )
        )
        hdl_files = tuple(
            _hdl_file(path) for path in _walk_files(config.repo_root, HDL_EXTENSIONS, excluded_roots=excluded_roots)
        )

    documentation_files = tuple(
        _dedupe_paths(path for configured in config.documentation_paths for path in _documentation_inputs(configured))
    )
    include_paths = tuple(_dedupe_paths((*config.include_paths, *filelist_include_paths)))
    defines = tuple(dict.fromkeys((*config.defines, *filelist_defines)))

    return ProjectInventory(
        hdl_files=hdl_files,
        documentation_files=documentation_files,
        include_paths=include_paths,
        defines=defines,
    )


def parse_filelist(path: Path, repo_root: Path) -> ProjectInventory:
    """Parse common Verilog file-list flags without invoking any tools."""

    filelist = normalize_path(path, repo_root)
    return _parse_filelist(filelist, repo_root, ())


def _parse_filelist(path: Path, repo_root: Path, stack: tuple[Path, ...]) -> ProjectInventory:
    filelist = normalize_path(path, repo_root)
    if filelist in stack:
        chain = " -> ".join(str(item) for item in (*stack, filelist))
        raise ValueError(f"Recursive RTL file list include detected: {chain}")

    base = filelist.parent
    hdl_files: list[Path] = []
    include_paths: list[Path] = []
    defines: list[str] = []

    tokens = _filelist_tokens(filelist)
    index = 0
    while index < len(tokens):
        token = tokens[index]
        if token.startswith("+incdir+"):
            include_paths.extend(
                normalize_path(include_path, base)
                for include_path in token.removeprefix("+incdir+").split("+")
                if include_path
            )
        elif token == "-I" and index + 1 < len(tokens):
            index += 1
            include_paths.append(normalize_path(tokens[index], base))
        elif token.startswith("-I") and len(token) > 2:
            include_paths.append(normalize_path(token[2:], base))
        elif token.startswith("+define+"):
            defines.extend(define for define in token.removeprefix("+define+").split("+") if define)
        elif token == "-D" and index + 1 < len(tokens):
            index += 1
            defines.append(tokens[index])
        elif token.startswith("-D") and len(token) > 2:
            defines.append(token[2:])
        elif token in {"-f", "-F"} and index + 1 < len(tokens):
            index += 1
            nested = _parse_filelist(normalize_path(tokens[index], base), repo_root, (*stack, filelist))
            hdl_files.extend(hdl_file.path for hdl_file in nested.hdl_files)
            include_paths.extend(nested.include_paths)
            defines.extend(nested.defines)
        elif (token.startswith("-f") or token.startswith("-F")) and len(token) > 2:
            nested = _parse_filelist(normalize_path(token[2:], base), repo_root, (*stack, filelist))
            hdl_files.extend(hdl_file.path for hdl_file in nested.hdl_files)
            include_paths.extend(nested.include_paths)
            defines.extend(nested.defines)
        elif token == "-v" and index + 1 < len(tokens):
            index += 1
            if Path(tokens[index]).suffix.lower() in HDL_EXTENSIONS:
                hdl_files.append(normalize_path(tokens[index], base))
        elif Path(token).suffix.lower() in HDL_EXTENSIONS:
            hdl_files.append(normalize_path(token, base))
        index += 1

    return ProjectInventory(
        hdl_files=tuple(_hdl_file(path) for path in _dedupe_paths(hdl_files)),
        documentation_files=(),
        include_paths=tuple(_dedupe_paths(include_paths)),
        defines=tuple(dict.fromkeys(defines)),
    )


def build_verilator_dry_run_command(config: CLIConfig, inventory: ProjectInventory) -> tuple[str, ...]:
    """Build the Verilator XML command used by dry-run and analysis execution."""

    command: list[str] = [
        *shlex.split(config.verilator_executable),
        "--xml-only",
        "--Mdir",
        str(config.work_dir / "verilator"),
    ]
    for include_path in inventory.include_paths:
        command.append(f"-I{include_path}")
    for define in inventory.defines:
        command.append(f"-D{define}")
    for override in config.parameter_overrides:
        command.append(f"-G{override}")
    for top_module in config.top_modules:
        command.extend(("--top-module", top_module))
    command.extend(str(hdl_file.path) for hdl_file in inventory.hdl_files)
    return tuple(command)


def write_project_manifest(
    config: CLIConfig,
    inventory: ProjectInventory,
    verilator_command: tuple[str, ...],
    diagnostics: tuple[ConfigDiagnostic, ...] = (),
) -> Path:
    """Persist a machine-readable project inventory under the work directory."""

    manifest_path = config.work_dir / "project-manifest.json"
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "repo_root": str(config.repo_root),
        "work_dir": str(config.work_dir),
        "output_dir": str(config.output_dir),
        "documentation_files": [str(path) for path in inventory.documentation_files],
        "hdl_files": [
            {"path": str(hdl_file.path), "language": hdl_file.language, "library": hdl_file.library}
            for hdl_file in inventory.hdl_files
        ],
        "include_paths": [str(path) for path in inventory.include_paths],
        "defines": list(inventory.defines),
        "parameter_overrides": list(config.parameter_overrides),
        "top_modules": list(config.top_modules),
        "verilator_command": list(verilator_command),
        "allow_network": config.allow_network,
        "strict": config.strict,
        "ci": config.ci,
        "diagnostics": [{"severity": diagnostic.severity, "message": diagnostic.message} for diagnostic in diagnostics],
    }
    atomic_write_text(manifest_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return manifest_path


def _filelist_tokens(path: Path) -> list[str]:
    tokens: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        stripped = _strip_comment(line).strip()
        if stripped:
            tokens.extend(shlex.split(stripped))
    return tokens


def _strip_comment(line: str) -> str:
    hash_index = line.find("#")
    slash_index = line.find("//")
    indexes = [index for index in (hash_index, slash_index) if index >= 0]
    if not indexes:
        return line
    return line[: min(indexes)]


def _documentation_inputs(path: Path) -> tuple[Path, ...]:
    if path.is_file() and path.suffix.lower() in DOCUMENTATION_EXTENSIONS:
        return (path,)
    if path.is_dir():
        return tuple(_walk_files(path, DOCUMENTATION_EXTENSIONS))
    return ()


def _walk_files(
    root: Path,
    extensions: set[str] | dict[str, str],
    excluded_roots: tuple[Path, ...] = (),
) -> tuple[Path, ...]:
    files: list[Path] = []
    for path in root.rglob("*"):
        if any(part in SKIPPED_DIRECTORIES for part in path.relative_to(root).parts[:-1]):
            continue
        if any(is_within(path, excluded) for excluded in excluded_roots):
            continue
        if path.is_file() and path.suffix.lower() in extensions:
            files.append(path.resolve(strict=False))
    return tuple(sorted(files, key=lambda item: item.as_posix()))


def _hdl_file(path: Path) -> HDLFile:
    return HDLFile(path=path, language=HDL_EXTENSIONS[path.suffix.lower()])


def _dedupe_paths(paths: Iterable[Path | str]) -> tuple[Path, ...]:
    return tuple(dict.fromkeys(Path(path).resolve(strict=False) for path in paths))
