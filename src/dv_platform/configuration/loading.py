"""Configuration loading, normalization, validation, and serialization."""

from __future__ import annotations

import tomllib
from pathlib import Path
from typing import Any

from dv_platform.configuration.parameters import expand_parameter_matrix
from dv_platform.domain.models import (
    AdapterPluginConfig,
    AIConfig,
    CLIConfig,
    ContextOptimizationConfig,
    CoveragePolicy,
    FormalToolConfig,
    ProductionProtocolBinding,
    ProtocolProfile,
    SimulatorConfig,
    VerificationDepthPolicy,
    VerificationTarget,
)


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
        register_map_paths=tuple(normalize_path(path, repo_root) for path in config.register_map_paths),
        rtl_filelists=tuple(normalize_path(path, repo_root) for path in config.rtl_filelists),
        include_paths=tuple(normalize_path(path, repo_root) for path in config.include_paths),
        defines=config.defines,
        parameter_overrides=config.parameter_overrides,
        parameter_sweeps=config.parameter_sweeps,
        parameter_matrix=config.parameter_matrix,
        parameter_constraints=config.parameter_constraints,
        max_parameter_points=config.max_parameter_points,
        cross_language_bindings=(
            normalize_path(config.cross_language_bindings, repo_root)
            if config.cross_language_bindings is not None
            else None
        ),
        top_modules=config.top_modules,
        verilator_executable=config.verilator_executable,
        slang_executable=config.slang_executable,
        semantic_crosscheck=config.semantic_crosscheck,
        retrieval_index_dir=retrieval_index_dir,
        allow_network=config.allow_network,
        strict=config.strict or config.ci,
        ci=config.ci,
        simulators=config.simulators,
        formal_tools=config.formal_tools,
        generator_plugins=config.generator_plugins,
        adapter_plugins=config.adapter_plugins,
        protocol_profiles=config.protocol_profiles,
        production_protocol_bindings=config.production_protocol_bindings,
        depth_policies=config.depth_policies,
        coverage_policy=config.coverage_policy,
        audit_enabled=config.audit_enabled,
        redact_patterns=config.redact_patterns,
        approved_plugin_publishers=config.approved_plugin_publishers,
        export_roots=tuple(normalize_path(path, repo_root) for path in config.export_roots) or (work_dir, output_dir),
        secret_provider=config.secret_provider,
        retention_days=config.retention_days,
        max_parallel_modules=config.max_parallel_modules,
        max_process_memory_mb=config.max_process_memory_mb,
        max_total_process_memory_mb=config.max_total_process_memory_mb,
        max_output_bytes=config.max_output_bytes,
        license_tokens=config.license_tokens,
        sandbox_enabled=config.sandbox_enabled,
        sandbox_runtime=config.sandbox_runtime,
        sandbox_image=config.sandbox_image,
        sandbox_environment=config.sandbox_environment,
        ai=config.ai,
        context_optimization=config.context_optimization,
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
        register_map_paths=(),
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
    ai = data.get("ai", {})
    records = _config_records(data)
    context_optimization = data.get("context_optimization", {})
    raw = _config_projection(
        paths, rtl, retrieval, policy, coverage, execution, security, plugins, ai, context_optimization, records
    )
    return normalize_config(raw, base=config_path.parent)


def _config_records(data: dict[str, Any]) -> dict[str, object]:
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
            publisher=_optional_nonempty_string(plugin.get("publisher")),
            package_sha256=_optional_nonempty_string(plugin.get("package_sha256")),
            signature_kind=_optional_nonempty_string(plugin.get("signature_kind")),
            signature_path=_optional_nonempty_string(plugin.get("signature_path")),
            certificate_identity=_optional_nonempty_string(plugin.get("certificate_identity")),
            certificate_issuer=_optional_nonempty_string(plugin.get("certificate_issuer")),
            trust_root=_optional_nonempty_string(plugin.get("trust_root")),
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
    production_protocol_bindings = tuple(
        ProductionProtocolBinding(
            profile_id=str(binding["profile_id"]),
            module=str(binding["module"]),
            instance_id=str(binding["instance_id"]),
            role=str(binding["role"]),
            aliases=tuple(sorted((str(name), str(signal)) for name, signal in binding.get("aliases", {}).items())),
        )
        for binding in data.get("production_protocol_bindings", ())
    )
    depth_policies = tuple(
        VerificationDepthPolicy(
            kind=str(policy["kind"]),
            module=str(policy["module"]),
            subject=str(policy["subject"]),
            parameters=tuple(
                sorted(
                    (str(key), _policy_parameter_value(value))
                    for key, value in policy.items()
                    if key not in {"kind", "module", "subject"}
                )
            ),
        )
        for policy in data.get("verification_depth", ())
    )

    return {
        "simulators": simulators,
        "formal_tools": formal_tools,
        "adapter_plugins": adapter_plugins,
        "protocol_profiles": protocol_profiles,
        "production_protocol_bindings": production_protocol_bindings,
        "depth_policies": depth_policies,
    }


def _config_projection(paths, rtl, retrieval, policy, coverage, execution, security, plugins, ai, context_optimization, records):
    simulators = records["simulators"]
    formal_tools = records["formal_tools"]
    adapter_plugins = records["adapter_plugins"]
    protocol_profiles = records["protocol_profiles"]
    production_protocol_bindings = records["production_protocol_bindings"]
    depth_policies = records["depth_policies"]
    raw = CLIConfig(
        repo_root=Path(paths.get("repo_root", ".")),
        work_dir=Path(paths.get("work_dir", ".dv-platform")),
        output_dir=Path(paths.get("output_dir", "generated/dv-platform")),
        documentation_paths=tuple(Path(path) for path in paths.get("documentation_paths", ())),
        register_map_paths=tuple(Path(path) for path in paths.get("register_map_paths", ())),
        rtl_filelists=tuple(Path(path) for path in paths.get("rtl_filelists", ())),
        include_paths=tuple(Path(path) for path in paths.get("include_paths", ())),
        defines=tuple(str(define) for define in rtl.get("defines", ())),
        parameter_overrides=tuple(str(item) for item in rtl.get("parameter_overrides", ())),
        parameter_sweeps=_unique_parameter_sweeps(
            tuple(tuple(str(item) for item in sweep) for sweep in rtl.get("parameter_sweeps", ()))
            + _configured_parameter_matrix(rtl)
        ),
        parameter_matrix=tuple(
            sorted(
                (str(name), tuple(str(value) for value in values))
                for name, values in rtl.get("parameter_matrix", {}).items()
            )
        ),
        parameter_constraints=tuple(str(item) for item in rtl.get("parameter_constraints", ())),
        max_parameter_points=int(rtl.get("max_parameter_points", 64)),
        cross_language_bindings=(
            Path(str(rtl["cross_language_bindings"])) if rtl.get("cross_language_bindings") is not None else None
        ),
        top_modules=tuple(str(module) for module in rtl.get("top_modules", ())),
        verilator_executable=str(rtl.get("verilator_executable", "verilator")),
        slang_executable=str(rtl.get("slang_executable", "slang")),
        semantic_crosscheck=str(rtl.get("semantic_crosscheck", "off")),
        retrieval_index_dir=Path(retrieval["index_dir"]) if "index_dir" in retrieval else None,
        allow_network=bool(policy.get("allow_network", False)),
        strict=bool(policy.get("strict", False)),
        ci=bool(policy.get("ci", False)),
        simulators=simulators,
        formal_tools=formal_tools,
        generator_plugins=tuple(str(plugin) for plugin in plugins.get("generator_backends", ())),
        adapter_plugins=adapter_plugins,
        protocol_profiles=protocol_profiles,
        production_protocol_bindings=production_protocol_bindings,
        depth_policies=depth_policies,
        coverage_policy=CoveragePolicy(
            line_minimum=_optional_percentage(coverage.get("line_minimum")),
            branch_minimum=_optional_percentage(coverage.get("branch_minimum")),
            toggle_minimum=_optional_percentage(coverage.get("toggle_minimum")),
            functional_minimum=_optional_percentage(coverage.get("functional_minimum")),
        ),
        audit_enabled=bool(security.get("audit_enabled", True)),
        redact_patterns=tuple(str(item) for item in security.get("redact_patterns", ())),
        approved_plugin_publishers=tuple(str(item) for item in security.get("approved_plugin_publishers", ())),
        export_roots=tuple(Path(item) for item in security.get("export_roots", ())),
        secret_provider=str(security.get("secret_provider", "environment")),
        retention_days=int(security.get("retention_days", 30)),
        max_parallel_modules=int(execution.get("max_parallel_modules", 1)),
        max_process_memory_mb=int(execution.get("max_process_memory_mb", 768)),
        max_total_process_memory_mb=int(execution.get("max_total_process_memory_mb", 4096)),
        max_output_bytes=int(execution.get("max_output_bytes", 1_048_576)),
        license_tokens=int(execution.get("license_tokens", 1)),
        sandbox_enabled=bool(execution.get("sandbox_enabled", False)),
        sandbox_runtime=str(execution.get("sandbox_runtime", "podman")),
        sandbox_image=_optional_nonempty_string(execution.get("sandbox_image")),
        sandbox_environment=tuple(str(item) for item in execution.get("sandbox_environment", ())),
        ai=_ai_config(ai),
        context_optimization=_context_optimization_config(context_optimization),
    )
    return raw


def _ai_config(ai) -> AIConfig:
    return AIConfig(
        model=str(ai.get("model", "")),
        api_key_env=_optional_nonempty_string(ai.get("api_key_env")),
        api_base=_optional_nonempty_string(ai.get("api_base")),
        api_version=_optional_nonempty_string(ai.get("api_version")),
        timeout_seconds=float(ai.get("timeout_seconds", 60)),
        max_retries=int(ai.get("max_retries", 2)),
        max_output_tokens=int(ai.get("max_output_tokens", 4096)),
        max_context_chars=int(ai.get("max_context_chars", 32000)),
        max_modules_per_run=int(ai.get("max_modules_per_run", 20)),
        cache=bool(ai.get("cache", True)),
        allowed_stages=tuple(str(item) for item in ai.get("allowed_stages", ("planning", "feedback_analysis"))),
        max_repair_attempts=int(ai.get("max_repair_attempts", 2)),
        fallback=str(ai.get("fallback", "deterministic")),
    )


def _context_optimization_config(context_optimization) -> ContextOptimizationConfig:
    return ContextOptimizationConfig(
        stages=tuple(str(item) for item in context_optimization.get("stages", ("planning", "feedback_analysis", "scenario_synthesis"))),
        headroom_endpoint=str(context_optimization.get("headroom_endpoint", "http://127.0.0.1:8787")),
        headroom_timeout_seconds=float(context_optimization.get("headroom_timeout_seconds", 5)),
        code_graph_command=str(context_optimization.get("code_graph_command", "code-review-graph")),
        code_graph_timeout_seconds=float(context_optimization.get("code_graph_timeout_seconds", 10)),
        code_graph_max_context_chars=int(context_optimization.get("code_graph_max_context_chars", 4000)),
        code_graph_detail_level=str(context_optimization.get("code_graph_detail_level", "minimal")),
        code_graph_auto_update=bool(context_optimization.get("code_graph_auto_update", False)),
    )


def _configured_parameter_matrix(rtl: dict[str, object]) -> tuple[tuple[str, ...], ...]:
    raw = rtl.get("parameter_matrix", {})
    if not isinstance(raw, dict) or not raw:
        return ()
    axes: list[tuple[str, tuple[str, ...]]] = []
    for name, values in raw.items():
        if not isinstance(values, list):
            raise ValueError(f"rtl.parameter_matrix.{name} must be an array")
        axes.append((str(name), tuple(str(value) for value in values)))
    constraints = rtl.get("parameter_constraints", ())
    if not isinstance(constraints, list):
        raise ValueError("rtl.parameter_constraints must be an array")
    return expand_parameter_matrix(
        tuple(axes),
        constraints=tuple(str(item) for item in constraints),
        maximum_points=int(str(rtl.get("max_parameter_points", 64))),
    )


def _unique_parameter_sweeps(sweeps: tuple[tuple[str, ...], ...]) -> tuple[tuple[str, ...], ...]:
    """Preserve configured order while preventing matrix/manual point duplication."""

    return tuple(dict.fromkeys(sweeps))


def _optional_percentage(value: object) -> float | None:
    return float(str(value)) if value is not None else None


def _optional_nonempty_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None


def _policy_parameter_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    return str(value)
