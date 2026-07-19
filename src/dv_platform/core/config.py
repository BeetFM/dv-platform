"""Configuration file loading and writing for the local CLI."""

from __future__ import annotations

import re
import shlex
import tomllib
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

from dv_platform.core.io import atomic_write_text
from dv_platform.core.literals import safe_sv_numeric_literal
from dv_platform.core.models import (
    AdapterPluginConfig,
    CLIConfig,
    CoveragePolicy,
    FormalToolConfig,
    ProtocolProfile,
    SimulatorConfig,
    VerificationTarget,
)

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
        parameter_overrides=config.parameter_overrides,
        top_modules=config.top_modules,
        verilator_executable=config.verilator_executable,
        retrieval_index_dir=retrieval_index_dir,
        allow_network=config.allow_network,
        strict=config.strict or config.ci,
        ci=config.ci,
        simulators=config.simulators,
        formal_tools=config.formal_tools,
        generator_plugins=config.generator_plugins,
        adapter_plugins=config.adapter_plugins,
        protocol_profiles=config.protocol_profiles,
        coverage_policy=config.coverage_policy,
        audit_enabled=config.audit_enabled,
        redact_patterns=config.redact_patterns,
        max_parallel_modules=config.max_parallel_modules,
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
    coverage = data.get("coverage", {})
    execution = data.get("execution", {})
    security = data.get("security", {})
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
    adapter_plugins = tuple(
        AdapterPluginConfig(
            kind=str(plugin["kind"]),
            name=str(plugin["name"]),
            api_version=int(plugin.get("api_version", 1)),
        )
        for plugin in data.get("adapter_plugins", ())
    )
    protocol_profiles = tuple(
        ProtocolProfile(
            name=str(profile["name"]),
            kind=str(profile.get("kind", "ready_valid")),
            valid_suffix=str(profile.get("valid_suffix", "_valid")),
            ready_suffix=str(profile.get("ready_suffix", "_ready")),
            data_suffixes=tuple(str(item) for item in profile.get("data_suffixes", ("_data", "_payload", "_bits"))),
        )
        for profile in data.get("protocol_profiles", ())
    )

    raw = CLIConfig(
        repo_root=Path(paths.get("repo_root", ".")),
        work_dir=Path(paths.get("work_dir", ".dv-platform")),
        output_dir=Path(paths.get("output_dir", "generated/dv-platform")),
        documentation_paths=tuple(Path(path) for path in paths.get("documentation_paths", ())),
        rtl_filelists=tuple(Path(path) for path in paths.get("rtl_filelists", ())),
        include_paths=tuple(Path(path) for path in paths.get("include_paths", ())),
        defines=tuple(str(define) for define in rtl.get("defines", ())),
        parameter_overrides=tuple(str(item) for item in rtl.get("parameter_overrides", ())),
        top_modules=tuple(str(module) for module in rtl.get("top_modules", ())),
        verilator_executable=str(rtl.get("verilator_executable", "verilator")),
        retrieval_index_dir=Path(retrieval["index_dir"]) if "index_dir" in retrieval else None,
        allow_network=bool(policy.get("allow_network", False)),
        strict=bool(policy.get("strict", False)),
        ci=bool(policy.get("ci", False)),
        simulators=simulators,
        formal_tools=formal_tools,
        generator_plugins=tuple(str(plugin) for plugin in plugins.get("generator_backends", ())),
        adapter_plugins=adapter_plugins,
        protocol_profiles=protocol_profiles,
        coverage_policy=CoveragePolicy(
            line_minimum=_optional_percentage(coverage.get("line_minimum")),
            branch_minimum=_optional_percentage(coverage.get("branch_minimum")),
            toggle_minimum=_optional_percentage(coverage.get("toggle_minimum")),
            functional_minimum=_optional_percentage(coverage.get("functional_minimum")),
        ),
        audit_enabled=bool(security.get("audit_enabled", True)),
        redact_patterns=tuple(str(item) for item in security.get("redact_patterns", ())),
        max_parallel_modules=int(execution.get("max_parallel_modules", 1)),
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
        diagnostics.append(
            ConfigDiagnostic("warning", "No top modules configured; analysis will rely on tool inference.")
        )

    parameter_names: set[str] = set()
    for override in config.parameter_overrides:
        name, separator, value = override.partition("=")
        if (
            not separator
            or not value.strip()
            or name != name.strip()
            or value != value.strip()
            or re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name.strip()) is None
            or not safe_sv_numeric_literal(value.strip())
        ):
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid parameter override {override!r}; expected NAME=VALUE.")
            )
            continue
        if name in parameter_names:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate parameter override: {name}"))
        parameter_names.add(name)
    if config.parameter_overrides and not config.top_modules:
        diagnostics.append(
            ConfigDiagnostic(
                "error" if strict else "warning",
                "Parameter overrides require an explicit top module so elaboration scope is deterministic.",
            )
        )

    if not _command_is_valid(config.verilator_executable):
        diagnostics.append(ConfigDiagnostic("error", "Verilator executable command must not be empty."))

    simulator_targets: set[VerificationTarget] = set()
    for simulator in config.simulators:
        if simulator.target in simulator_targets:
            diagnostics.append(
                ConfigDiagnostic("error", f"More than one simulator is configured for target {simulator.target}.")
            )
        simulator_targets.add(simulator.target)
        if not simulator.name.strip() or not _command_is_valid(simulator.command):
            diagnostics.append(
                ConfigDiagnostic("error", f"Simulator name and command must not be empty: {simulator.target}")
            )

    formal_names: set[str] = set()
    for tool in config.formal_tools:
        if tool.name in formal_names:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate formal tool configuration: {tool.name}"))
        formal_names.add(tool.name)
        if not tool.name.strip() or not _command_is_valid(tool.command):
            diagnostics.append(ConfigDiagnostic("error", "Formal tool name and command must not be empty."))
    if len(config.formal_tools) > 1:
        diagnostics.append(
            ConfigDiagnostic("error", "More than one formal tool is configured; selection is ambiguous.")
        )

    if not 1 <= config.max_parallel_modules <= 256:
        diagnostics.append(ConfigDiagnostic("error", "execution.max_parallel_modules must be between 1 and 256."))

    for coverage_name, coverage_value in (
        ("line_minimum", config.coverage_policy.line_minimum),
        ("branch_minimum", config.coverage_policy.branch_minimum),
        ("toggle_minimum", config.coverage_policy.toggle_minimum),
        ("functional_minimum", config.coverage_policy.functional_minimum),
    ):
        if coverage_value is not None and not 0.0 <= coverage_value <= 100.0:
            diagnostics.append(ConfigDiagnostic("error", f"coverage.{coverage_name} must be between 0 and 100."))

    profile_names: set[str] = set()
    for profile in config.protocol_profiles:
        if profile.name in profile_names:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate protocol profile: {profile.name}"))
        profile_names.add(profile.name)
        if profile.kind not in {"ready_valid", "req_ack"}:
            diagnostics.append(ConfigDiagnostic("error", f"Unsupported protocol profile kind: {profile.kind}"))
        suffixes = (profile.valid_suffix, profile.ready_suffix, *profile.data_suffixes)
        if not profile.name.strip() or any(re.fullmatch(r"_[A-Za-z0-9_]+", suffix) is None for suffix in suffixes):
            diagnostics.append(ConfigDiagnostic("error", f"Invalid signal suffix in protocol profile: {profile.name}"))

    plugin_keys: set[tuple[str, str]] = set()
    supported_plugin_kinds = {
        "generator",
        "simulator_runner",
        "formal_runner",
        "document_loader",
        "embedding_provider",
        "vector_store",
        "report_exporter",
        "redaction_policy",
    }
    for plugin in config.adapter_plugins:
        key = (plugin.kind, plugin.name)
        if key in plugin_keys:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate adapter plugin: {plugin.kind}/{plugin.name}"))
        plugin_keys.add(key)
        if plugin.kind not in supported_plugin_kinds or not plugin.name.strip():
            diagnostics.append(ConfigDiagnostic("error", f"Invalid adapter plugin: {plugin.kind}/{plugin.name}"))
        if plugin.api_version != 1:
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"Unsupported adapter API version for {plugin.kind}/{plugin.name}: {plugin.api_version}"
                )
            )

    for pattern in config.redact_patterns:
        try:
            re.compile(pattern)
        except re.error as error:
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid security.redact_patterns entry {pattern!r}: {error}")
            )

    return tuple(diagnostics)


def validate_target_tools(config: CLIConfig, targets: tuple[VerificationTarget, ...]) -> tuple[ConfigDiagnostic, ...]:
    """Return tool-configuration diagnostics for target-specific commands."""

    diagnostics: list[ConfigDiagnostic] = []
    strict = config.strict or config.ci
    if VerificationTarget.FORMAL in targets and len(config.formal_tools) > 1:
        diagnostics.append(
            ConfigDiagnostic("error", "More than one formal tool is configured; selection is ambiguous.")
        )
    if strict and VerificationTarget.FORMAL in targets and not config.formal_tools:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                f"No formal tools configured for target {VerificationTarget.FORMAL}; add [[formal_tools]] to {DEFAULT_CONFIG_FILENAME}.",
            )
        )
    for target in targets:
        if target == VerificationTarget.FORMAL:
            for tool in config.formal_tools:
                if not tool.name.strip() or not _command_is_valid(tool.command):
                    diagnostics.append(ConfigDiagnostic("error", "Formal tool name and command must not be empty."))
            continue
        matching_simulators = tuple(item for item in config.simulators if item.target == target)
        if len(matching_simulators) > 1:
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"More than one simulator is configured for target {target}; selection is ambiguous."
                )
            )
        for simulator in matching_simulators:
            if not simulator.name.strip() or not _command_is_valid(simulator.command):
                diagnostics.append(
                    ConfigDiagnostic("error", f"Simulator name and command must not be empty for target {target}.")
                )
    return tuple(diagnostics)


def _command_is_valid(command: str) -> bool:
    try:
        return bool(shlex.split(command))
    except ValueError:
        return False


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
            f"parameter_overrides = {_toml_array(normalized.parameter_overrides)}",
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
            "[coverage]",
            *_optional_toml_float("line_minimum", normalized.coverage_policy.line_minimum),
            *_optional_toml_float("branch_minimum", normalized.coverage_policy.branch_minimum),
            *_optional_toml_float("toggle_minimum", normalized.coverage_policy.toggle_minimum),
            *_optional_toml_float("functional_minimum", normalized.coverage_policy.functional_minimum),
            "",
            "[execution]",
            f"max_parallel_modules = {normalized.max_parallel_modules}",
            "",
            "[security]",
            f"audit_enabled = {_toml_bool(normalized.audit_enabled)}",
            f"redact_patterns = {_toml_array(normalized.redact_patterns)}",
            "",
            "[plugins]",
            f"generator_backends = {_toml_array(normalized.generator_plugins)}",
            "",
            *(
                line
                for plugin in normalized.adapter_plugins
                for line in (
                    "[[adapter_plugins]]",
                    f'kind = "{_escape(plugin.kind)}"',
                    f'name = "{_escape(plugin.name)}"',
                    f"api_version = {plugin.api_version}",
                    "",
                )
            ),
            *(
                line
                for profile in normalized.protocol_profiles
                for line in (
                    "[[protocol_profiles]]",
                    f'name = "{_escape(profile.name)}"',
                    f'kind = "{_escape(profile.kind)}"',
                    f'valid_suffix = "{_escape(profile.valid_suffix)}"',
                    f'ready_suffix = "{_escape(profile.ready_suffix)}"',
                    f"data_suffixes = {_toml_array(profile.data_suffixes)}",
                    "",
                )
            ),
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
    atomic_write_text(config_path, text)


def _toml_array(values: Iterable[object]) -> str:
    return "[" + ", ".join(f'"{_escape(str(value))}"' for value in values) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


def _optional_percentage(value: object) -> float | None:
    return float(str(value)) if value is not None else None


def _optional_toml_float(name: str, value: float | None) -> tuple[str, ...]:
    return (f"{name} = {value:g}",) if value is not None else ()


def _toml_path(path: Path, base: Path) -> str:
    try:
        value = path.relative_to(base)
    except ValueError:
        value = path
    return _escape(value.as_posix())


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"')
