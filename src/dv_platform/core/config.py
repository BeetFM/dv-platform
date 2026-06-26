"""Configuration file loading and writing for the local CLI."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path
import tomllib

from dv_platform.core.models import CLIConfig, FormalToolConfig, SimulatorConfig, VerificationTarget


DEFAULT_CONFIG_FILENAME = "dv-platform.toml"


@dataclass(frozen=True)
class ConfigDiagnostic:
    """A validation message for local project configuration."""

    severity: str
    message: str


def normalize_path(path: Path | str, base: Path) -> Path:
    """Return an absolute, user-expanded path without requiring it to exist."""

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def normalize_config(config: CLIConfig, base: Path | None = None) -> CLIConfig:
    """Normalize all path fields in a CLI configuration."""

    root_base = base.resolve(strict=False) if base is not None else Path.cwd()
    repo_root = normalize_path(config.repo_root, root_base)

    work_dir = normalize_path(config.work_dir, repo_root)
    output_dir = normalize_path(config.output_dir, repo_root)
    retrieval_index_dir = (
        normalize_path(config.retrieval_index_dir, repo_root)
        if config.retrieval_index_dir is not None
        else work_dir / "rag-index"
    )

    return CLIConfig(
        repo_root=repo_root,
        work_dir=work_dir,
        output_dir=output_dir,
        documentation_paths=tuple(normalize_path(path, repo_root) for path in config.documentation_paths),
        rtl_filelists=tuple(normalize_path(path, repo_root) for path in config.rtl_filelists),
        include_paths=tuple(normalize_path(path, repo_root) for path in config.include_paths),
        defines=config.defines,
        top_modules=config.top_modules,
        verilator_executable=config.verilator_executable,
        retrieval_index_dir=retrieval_index_dir,
        allow_network=config.allow_network,
        strict=config.strict or config.ci,
        ci=config.ci,
        simulators=config.simulators,
        formal_tools=config.formal_tools,
        generator_plugins=config.generator_plugins,
    )


def default_config(repo_root: Path) -> CLIConfig:
    """Create a default local-only configuration rooted at an RTL repository."""

    normalized_root = normalize_path(repo_root, Path.cwd())
    documentation_paths: tuple[Path, ...] = ()
    if (normalized_root / "docs").is_dir():
        documentation_paths = (normalized_root / "docs",)

    return CLIConfig(
        repo_root=normalized_root,
        work_dir=normalized_root / ".dv-platform",
        output_dir=normalized_root / "generated" / "dv-platform",
        documentation_paths=documentation_paths,
        retrieval_index_dir=normalized_root / ".dv-platform" / "rag-index",
    )


def load_config(path: Path) -> CLIConfig:
    """Load a TOML config file and normalize relative paths."""

    config_path = path.expanduser().resolve(strict=False)
    data = tomllib.loads(config_path.read_text(encoding="utf-8"))

    paths = data.get("paths", {})
    rtl = data.get("rtl", {})
    retrieval = data.get("retrieval", {})
    policy = data.get("policy", {})
    plugins = data.get("plugins", {})
    simulators = tuple(
        SimulatorConfig(
            target=VerificationTarget(str(simulator["target"])),
            name=str(simulator["name"]),
            command=str(simulator["command"]),
        )
        for simulator in data.get("simulators", ())
    )
    formal_tools = tuple(
        FormalToolConfig(
            name=str(tool["name"]),
            command=str(tool["command"]),
        )
        for tool in data.get("formal_tools", ())
    )

    raw = CLIConfig(
        repo_root=Path(paths.get("repo_root", ".")),
        work_dir=Path(paths.get("work_dir", ".dv-platform")),
        output_dir=Path(paths.get("output_dir", "generated/dv-platform")),
        documentation_paths=tuple(Path(path) for path in paths.get("documentation_paths", ())),
        rtl_filelists=tuple(Path(path) for path in paths.get("rtl_filelists", ())),
        include_paths=tuple(Path(path) for path in paths.get("include_paths", ())),
        defines=tuple(str(define) for define in rtl.get("defines", ())),
        top_modules=tuple(str(module) for module in rtl.get("top_modules", ())),
        verilator_executable=str(rtl.get("verilator_executable", "verilator")),
        retrieval_index_dir=Path(retrieval["index_dir"]) if "index_dir" in retrieval else None,
        allow_network=bool(policy.get("allow_network", False)),
        strict=bool(policy.get("strict", False)),
        ci=bool(policy.get("ci", False)),
        simulators=simulators,
        formal_tools=formal_tools,
        generator_plugins=tuple(str(plugin) for plugin in plugins.get("generator_backends", ())),
    )
    return normalize_config(raw, base=config_path.parent)


def validate_config(config: CLIConfig) -> tuple[ConfigDiagnostic, ...]:
    """Return deterministic configuration diagnostics for input-consuming commands."""

    diagnostics: list[ConfigDiagnostic] = []
    strict = config.strict or config.ci

    if not config.repo_root.is_dir():
        diagnostics.append(ConfigDiagnostic("error", f"Repository root does not exist: {config.repo_root}"))

    if not config.rtl_filelists:
        severity = "error" if strict else "warning"
        diagnostics.append(
            ConfigDiagnostic(
                severity,
                "No RTL file lists configured; walking repository HDL files directly may be incomplete.",
            )
        )

    for filelist in config.rtl_filelists:
        if not filelist.is_file():
            diagnostics.append(ConfigDiagnostic("error", f"RTL file list does not exist: {filelist}"))

    for include_path in config.include_paths:
        if not include_path.is_dir():
            severity = "error" if strict else "warning"
            diagnostics.append(ConfigDiagnostic(severity, f"Include path does not exist: {include_path}"))

    for documentation_path in config.documentation_paths:
        if not documentation_path.exists():
            diagnostics.append(ConfigDiagnostic("warning", f"Documentation path does not exist: {documentation_path}"))

    if not config.top_modules:
        diagnostics.append(ConfigDiagnostic("warning", "No top modules configured; analysis will rely on tool inference."))

    return tuple(diagnostics)


def validate_target_tools(config: CLIConfig, targets: tuple[VerificationTarget, ...]) -> tuple[ConfigDiagnostic, ...]:
    """Return tool-configuration diagnostics for target-specific commands."""

    diagnostics: list[ConfigDiagnostic] = []
    strict = config.strict or config.ci
    if strict and VerificationTarget.FORMAL in targets and not config.formal_tools:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                f"No formal tools configured for target {VerificationTarget.FORMAL}; add [[formal_tools]] to {DEFAULT_CONFIG_FILENAME}.",
            )
        )
    return tuple(diagnostics)


def write_config(config: CLIConfig, path: Path) -> None:
    """Write a deterministic TOML config file."""

    config_path = path.expanduser().resolve(strict=False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_config(config, base=config_path.parent)

    text = "\n".join(
        (
            "# dv-platform local project configuration",
            "",
            "[paths]",
            f'repo_root = "{_toml_path(normalized.repo_root, config_path.parent)}"',
            f'work_dir = "{_toml_path(normalized.work_dir, normalized.repo_root)}"',
            f'output_dir = "{_toml_path(normalized.output_dir, normalized.repo_root)}"',
            f"documentation_paths = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.documentation_paths)}",
            f"rtl_filelists = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.rtl_filelists)}",
            f"include_paths = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.include_paths)}",
            "",
            "[rtl]",
            f"defines = {_toml_array(normalized.defines)}",
            f"top_modules = {_toml_array(normalized.top_modules)}",
            f'verilator_executable = "{_escape(normalized.verilator_executable)}"',
            "",
            "[retrieval]",
            f'index_dir = "{_toml_path(normalized.retrieval_index_dir or normalized.work_dir / "rag-index", normalized.repo_root)}"',
            "",
            "[policy]",
            f"allow_network = {_toml_bool(normalized.allow_network)}",
            f"strict = {_toml_bool(normalized.strict)}",
            f"ci = {_toml_bool(normalized.ci)}",
            "",
            "[plugins]",
            f"generator_backends = {_toml_array(normalized.generator_plugins)}",
            "",
            *(
                line
                for simulator in normalized.simulators
                for line in (
                    "[[simulators]]",
                    f'target = "{_escape(str(simulator.target))}"',
                    f'name = "{_escape(simulator.name)}"',
                    f'command = "{_escape(simulator.command)}"',
                    "",
                )
            ),
            *(
                line
                for tool in normalized.formal_tools
                for line in (
                    "[[formal_tools]]",
                    f'name = "{_escape(tool.name)}"',
                    f'command = "{_escape(tool.command)}"',
                    "",
                )
            ),
        )
    )
    config_path.write_text(text, encoding="utf-8")


def _toml_array(values: Iterable[object]) -> str:
    return "[" + ", ".join(f'"{_escape(str(value))}"' for value in values) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _toml_path(path: Path, base: Path) -> str:
    try:
        value = path.relative_to(base)
    except ValueError:
        value = path
    return _escape(value.as_posix())


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
