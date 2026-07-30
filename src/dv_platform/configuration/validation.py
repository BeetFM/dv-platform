"""Configuration loading, normalization, validation, and serialization."""

from __future__ import annotations

import re
import shlex
from urllib.parse import parse_qsl, urlsplit

from dv_platform.configuration.depth_catalog import DEPTH_ALLOWED_PARAMETERS as _DEPTH_ALLOWED_PARAMETERS
from dv_platform.configuration.shared import DEFAULT_CONFIG_FILENAME, ConfigDiagnostic
from dv_platform.configuration.validation_depth_helpers import (
    validate_boolean as _validate_boolean,
)
from dv_platform.configuration.validation_depth_helpers import (
    validate_bounded_integer as _validate_bounded_integer,
)
from dv_platform.configuration.validation_depth_helpers import (
    validate_cdc_depth as _validate_cdc_depth,
)
from dv_platform.domain.literals import safe_sv_numeric_literal
from dv_platform.domain.models import (
    AIConfig,
    CLIConfig,
    VerificationDepthPolicy,
    VerificationTarget,
)
from dv_platform.domain.peripherals import PERIPHERAL_CONTRACTS, peripheral_parameter_names  # noqa: F401


def validate_config(config: CLIConfig) -> tuple[ConfigDiagnostic, ...]:
    """Return deterministic configuration diagnostics for input-consuming commands."""

    diagnostics: list[ConfigDiagnostic] = []
    strict = config.strict or config.ci
    _validate_input_paths(config, diagnostics, strict)
    _validate_parameters(config, diagnostics, strict)
    _validate_frontends_and_bindings(config, diagnostics)
    _validate_tool_selection(config, diagnostics)
    _validate_execution(config, diagnostics)
    _validate_coverage_and_profiles(config, diagnostics)
    _validate_depth_and_plugins(config, diagnostics)
    _validate_security(config, diagnostics)
    return tuple(diagnostics)


def _validate_input_paths(config: CLIConfig, diagnostics: list[ConfigDiagnostic], strict: bool) -> None:
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

    for register_map_path in config.register_map_paths:
        if not register_map_path.is_file():
            diagnostics.append(ConfigDiagnostic("error", f"Register map does not exist: {register_map_path}"))

    if not config.top_modules:
        diagnostics.append(
            ConfigDiagnostic("warning", "No top modules configured; analysis will rely on tool inference.")
        )


def _validate_parameters(config: CLIConfig, diagnostics: list[ConfigDiagnostic], strict: bool) -> None:
    parameter_names: set[str] = set()
    for override in config.parameter_overrides:
        name = _parameter_override_name(override)
        if name is None:
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid parameter override {override!r}; expected NAME=VALUE.")
            )
            continue
        if name in parameter_names:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate parameter override: {name}"))
        parameter_names.add(name)
    _validate_parameter_modes(config, diagnostics, strict)
    _validate_parameter_sweeps(config, diagnostics)


def _validate_parameter_modes(config: CLIConfig, diagnostics: list[ConfigDiagnostic], strict: bool) -> None:
    if config.parameter_overrides and not config.top_modules:
        diagnostics.append(
            ConfigDiagnostic(
                "error" if strict else "warning",
                "Parameter overrides require an explicit top module so elaboration scope is deterministic.",
            )
        )
    if config.parameter_overrides and config.parameter_sweeps:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "parameter_overrides and parameter_sweeps are mutually exclusive; choose one elaboration mode.",
            )
        )
    if config.parameter_sweeps and not config.top_modules:
        diagnostics.append(
            ConfigDiagnostic(
                "error" if strict else "warning",
                "Parameter sweeps require an explicit top module so elaboration scope is deterministic.",
            )
        )


def _validate_parameter_sweeps(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    sweep_signatures: set[str] = set()
    for sweep_index, sweep in enumerate(config.parameter_sweeps, start=1):
        names: set[str] = set()
        if not sweep:
            diagnostics.append(ConfigDiagnostic("error", f"Parameter sweep {sweep_index} is empty."))
        for override in sweep:
            name = _parameter_override_name(override)
            if name is None:
                diagnostics.append(
                    ConfigDiagnostic(
                        "error",
                        f"Invalid parameter override in sweep {sweep_index}: {override!r}; expected NAME=VALUE.",
                    )
                )
                continue
            if name in names:
                diagnostics.append(
                    ConfigDiagnostic("error", f"Duplicate parameter override in sweep {sweep_index}: {name}")
                )
            names.add(name)
        signature = ",".join(sweep)
        if signature in sweep_signatures:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate parameter sweep: {signature}"))
        sweep_signatures.add(signature)


def _parameter_override_name(override: str) -> str | None:
    name, separator, value = override.partition("=")
    if not separator or not value.strip() or name != name.strip() or value != value.strip():
        return None
    if re.fullmatch(r"[A-Za-z_$][A-Za-z0-9_$]*", name) is None or not safe_sv_numeric_literal(value):
        return None
    return name


def _validate_frontends_and_bindings(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    if not _command_is_valid(config.verilator_executable):
        diagnostics.append(ConfigDiagnostic("error", "Verilator executable command must not be empty."))
    if config.semantic_crosscheck not in {"off", "report", "required"}:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "rtl.semantic_crosscheck must be one of: off, report, required.",
            )
        )
    if not 1 <= config.max_parameter_points <= 4096:
        diagnostics.append(ConfigDiagnostic("error", "rtl.max_parameter_points must be between 1 and 4096."))
    if config.cross_language_bindings is not None and not config.cross_language_bindings.is_file():
        diagnostics.append(
            ConfigDiagnostic("error", f"rtl.cross_language_bindings is not a file: {config.cross_language_bindings}")
        )
    if config.semantic_crosscheck != "off" and not _command_is_valid(config.slang_executable):
        diagnostics.append(ConfigDiagnostic("error", "Slang executable command must not be empty."))

    binding_identities: set[tuple[str, str]] = set()
    for binding in config.production_protocol_bindings:
        from dv_platform.agent.protocols import protocol_profile

        try:
            production_profile = protocol_profile(binding.profile_id)
        except ValueError as error:
            diagnostics.append(ConfigDiagnostic("error", str(error)))
            continue
        identity = (binding.module, binding.instance_id)
        if identity in binding_identities:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate production protocol binding: {identity}"))
        binding_identities.add(identity)
        if not binding.module or not binding.instance_id or binding.role not in production_profile.roles:
            diagnostics.append(ConfigDiagnostic("error", f"Invalid production protocol binding: {identity}"))
        if not binding.aliases or len({signal for _name, signal in binding.aliases}) != len(binding.aliases):
            diagnostics.append(
                ConfigDiagnostic("error", f"Production protocol aliases must be non-empty and unique: {identity}")
            )


def _validate_tool_selection(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
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


def _validate_execution(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    if not 1 <= config.max_parallel_modules <= 256:
        diagnostics.append(ConfigDiagnostic("error", "execution.max_parallel_modules must be between 1 and 256."))
    if not 128 <= config.max_process_memory_mb <= 65536:
        diagnostics.append(ConfigDiagnostic("error", "execution.max_process_memory_mb must be between 128 and 65536."))
    if config.max_total_process_memory_mb < 2 * config.max_process_memory_mb:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "execution.max_total_process_memory_mb must be at least twice max_process_memory_mb "
                "because formal runs launch prove and cover tasks.",
            )
        )
    if not 1024 <= config.max_output_bytes <= 64 * 1024 * 1024:
        diagnostics.append(ConfigDiagnostic("error", "execution.max_output_bytes must be between 1024 and 67108864."))
    if not 1 <= config.license_tokens <= 1024:
        diagnostics.append(ConfigDiagnostic("error", "execution.license_tokens must be between 1 and 1024."))
    if config.sandbox_enabled and (config.sandbox_runtime not in {"podman", "docker"} or not config.sandbox_image):
        diagnostics.append(
            ConfigDiagnostic("error", "sandbox execution requires podman/docker and execution.sandbox_image.")
        )
    if any(re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) is None for name in config.sandbox_environment):
        diagnostics.append(ConfigDiagnostic("error", "execution.sandbox_environment contains an invalid name."))

    diagnostics.extend(validate_ai_config(config.ai, require_model=False))
    diagnostics.extend(validate_context_optimization_config(config.context_optimization))


def _validate_coverage_and_profiles(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
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


def _validate_depth_and_plugins(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    depth_keys: set[tuple[str, str, str]] = set()
    for policy in config.depth_policies:
        depth_key = (policy.kind, policy.module, policy.subject)
        if depth_key in depth_keys:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate verification depth policy: {'/'.join(depth_key)}"))
        depth_keys.add(depth_key)
        diagnostics.extend(_validate_depth_policy(policy))

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
        "coverage_importer",
        "semantic_importer",
        "requirements_importer",
        "analyzer_runner",
    }
    for plugin in config.adapter_plugins:
        key = (plugin.kind, plugin.name)
        if key in plugin_keys:
            diagnostics.append(ConfigDiagnostic("error", f"Duplicate adapter plugin: {plugin.kind}/{plugin.name}"))
        plugin_keys.add(key)
        if plugin.kind not in supported_plugin_kinds or not plugin.name.strip():
            diagnostics.append(ConfigDiagnostic("error", f"Invalid adapter plugin: {plugin.kind}/{plugin.name}"))
        if plugin.api_version not in {1, 2}:
            diagnostics.append(
                ConfigDiagnostic(
                    "error", f"Unsupported adapter API version for {plugin.kind}/{plugin.name}: {plugin.api_version}"
                )
            )
        if plugin.signature_kind not in {None, "sigstore", "pki"}:
            diagnostics.append(ConfigDiagnostic("error", f"Unsupported plugin signature kind: {plugin.name}"))
        if plugin.signature_kind == "sigstore" and not (
            plugin.signature_path and plugin.certificate_identity and plugin.certificate_issuer
        ):
            diagnostics.append(ConfigDiagnostic("error", f"Sigstore plugin trust policy is incomplete: {plugin.name}"))
        if plugin.signature_kind == "pki" and not (plugin.signature_path and plugin.trust_root):
            diagnostics.append(ConfigDiagnostic("error", f"PKI plugin trust policy is incomplete: {plugin.name}"))


def _validate_security(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    _validate_redaction_and_retention(config, diagnostics)
    _validate_plugin_publishers(config, diagnostics)


def _validate_redaction_and_retention(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    for pattern in config.redact_patterns:
        try:
            re.compile(pattern)
        except re.error as error:
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid security.redact_patterns entry {pattern!r}: {error}")
            )

    if config.secret_provider != "environment":
        diagnostics.append(ConfigDiagnostic("error", "security.secret_provider must be environment."))
    if not 1 <= config.retention_days <= 3650:
        diagnostics.append(ConfigDiagnostic("error", "security.retention_days must be between 1 and 3650."))
    if len(set(config.approved_plugin_publishers)) != len(config.approved_plugin_publishers) or any(
        not publisher.strip() for publisher in config.approved_plugin_publishers
    ):
        diagnostics.append(
            ConfigDiagnostic("error", "security.approved_plugin_publishers must be unique and non-empty.")
        )
    for root in config.export_roots:
        if not root.is_absolute():
            diagnostics.append(ConfigDiagnostic("error", f"security.export_roots entry must be absolute: {root}"))


def _validate_plugin_publishers(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    for plugin in config.adapter_plugins:
        if plugin.publisher is not None and plugin.publisher not in config.approved_plugin_publishers:
            diagnostics.append(
                ConfigDiagnostic(
                    "error",
                    f"Adapter plugin publisher is not approved for {plugin.kind}/{plugin.name}: {plugin.publisher}",
                )
            )
        if plugin.package_sha256 is not None and re.fullmatch(r"[0-9a-f]{64}", plugin.package_sha256) is None:
            diagnostics.append(ConfigDiagnostic("error", f"Invalid package SHA-256 for {plugin.kind}/{plugin.name}."))

    trusted_generators = {plugin.name for plugin in config.adapter_plugins if plugin.kind == "generator"}
    for plugin_name in config.generator_plugins:
        if plugin_name not in trusted_generators:
            diagnostics.append(
                ConfigDiagnostic(
                    "error",
                    f"Generator plugin requires a matching trusted [[adapter_plugins]] record: {plugin_name}",
                )
            )


def validate_ai_config(ai: AIConfig, require_model: bool = True) -> tuple[ConfigDiagnostic, ...]:
    """Validate the optional AI planner configuration without resolving credentials."""

    diagnostics: list[ConfigDiagnostic] = []
    if require_model and not ai.model.strip():
        diagnostics.append(ConfigDiagnostic("error", "ai.model must be configured for plan --ai."))
    if ai.model != ai.model.strip() or len(ai.model) > 512 or any(ord(character) < 32 for character in ai.model):
        diagnostics.append(
            ConfigDiagnostic(
                "error", "ai.model must be at most 512 characters without surrounding or control whitespace."
            )
        )
    if ai.api_key_env is not None and re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", ai.api_key_env) is None:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_key_env must be an environment variable name."))
    if ai.api_key_env is not None and len(ai.api_key_env) > 128:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_key_env must be at most 128 characters."))
    if ai.api_version is not None and (
        ai.api_version != ai.api_version.strip()
        or len(ai.api_version) > 128
        or any(ord(character) < 32 for character in ai.api_version)
    ):
        diagnostics.append(
            ConfigDiagnostic(
                "error", "ai.api_version must be at most 128 characters without surrounding or control whitespace."
            )
        )
    diagnostics.extend(_validate_ai_endpoint(ai.api_base))
    diagnostics.extend(_validate_ai_bounds(ai))
    return tuple(diagnostics)


def validate_context_optimization_config(context_optimization) -> tuple[ConfigDiagnostic, ...]:
    """Validate disabled-by-default external context optimizer settings."""

    diagnostics: list[ConfigDiagnostic] = []
    modes = (context_optimization.headroom_mode, context_optimization.code_graph_mode)
    if any(mode not in {"off", "advisory", "required"} for mode in modes):
        diagnostics.append(ConfigDiagnostic("error", "context_optimization modes must be off, advisory, or required."))
    known_stages = {"planning", "scenario_synthesis", "feedback_analysis"}
    if (
        not context_optimization.stages
        or len(set(context_optimization.stages)) != len(context_optimization.stages)
        or not set(context_optimization.stages) <= known_stages
    ):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "context_optimization.stages must be a non-empty unique subset of planning, "
                "scenario_synthesis, feedback_analysis.",
            )
        )
    diagnostics.extend(_validate_headroom_endpoint(context_optimization.headroom_endpoint))
    if not 1.0 <= context_optimization.headroom_timeout_seconds <= 60.0:
        diagnostics.append(
            ConfigDiagnostic("error", "context_optimization.headroom_timeout_seconds must be between 1 and 60.")
        )
    if not _command_is_valid(context_optimization.code_graph_command):
        diagnostics.append(ConfigDiagnostic("error", "context_optimization.code_graph_command must not be empty."))
    if not 1.0 <= context_optimization.code_graph_timeout_seconds <= 120.0:
        diagnostics.append(
            ConfigDiagnostic("error", "context_optimization.code_graph_timeout_seconds must be between 1 and 120.")
        )
    if not 512 <= context_optimization.code_graph_max_context_chars <= 100_000:
        diagnostics.append(
            ConfigDiagnostic(
                "error", "context_optimization.code_graph_max_context_chars must be between 512 and 100000."
            )
        )
    if context_optimization.code_graph_detail_level not in {"minimal", "standard"}:
        diagnostics.append(
            ConfigDiagnostic("error", "context_optimization.code_graph_detail_level must be one of: minimal, standard.")
        )
    return tuple(diagnostics)


def _validate_headroom_endpoint(endpoint: str) -> tuple[ConfigDiagnostic, ...]:
    diagnostics: list[ConfigDiagnostic] = []
    if endpoint != endpoint.strip() or len(endpoint) > 2048 or any(ord(character) < 32 for character in endpoint):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "context_optimization.headroom_endpoint must be at most 2048 characters without surrounding "
                "or control whitespace.",
            )
        )
    try:
        parsed = urlsplit(endpoint)
        parsed_port = parsed.port
    except ValueError:
        return (*diagnostics, ConfigDiagnostic("error", "context_optimization.headroom_endpoint must be valid."))
    if parsed.scheme != "http" or parsed.hostname not in {"localhost", "127.0.0.1", "::1"}:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "context_optimization.headroom_endpoint must be local HTTP: localhost, 127.0.0.1, or ::1.",
            )
        )
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        diagnostics.append(
            ConfigDiagnostic("error", "context_optimization.headroom_endpoint contains an invalid port.")
        )
    if parsed.username is not None or parsed.password is not None or parsed.query or parsed.fragment:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "context_optimization.headroom_endpoint must not contain credentials, query string, or fragment.",
            )
        )
    return tuple(diagnostics)


def _validate_ai_endpoint(api_base: str | None) -> tuple[ConfigDiagnostic, ...]:
    if api_base is None:
        return ()
    diagnostics: list[ConfigDiagnostic] = []
    if api_base != api_base.strip() or len(api_base) > 2048 or any(ord(character) < 32 for character in api_base):
        diagnostics.append(
            ConfigDiagnostic(
                "error", "ai.api_base must be at most 2048 characters without surrounding or control whitespace."
            )
        )
    try:
        parsed = urlsplit(api_base)
        parsed_port = parsed.port
    except ValueError:
        return (*diagnostics, ConfigDiagnostic("error", "ai.api_base must be a valid HTTP(S) URL."))
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_base must be an absolute HTTP(S) URL."))
    if parsed_port is not None and not 1 <= parsed_port <= 65535:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_base contains an invalid port."))
    if parsed.username is not None or parsed.password is not None:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_base must not contain embedded credentials."))
    sensitive_query_names = {
        "access_token",
        "api-key",
        "api_key",
        "apikey",
        "auth",
        "credential",
        "key",
        "password",
        "secret",
        "sig",
        "signature",
        "token",
        "x-api-key",
    }
    if any(name.lower() in sensitive_query_names for name, _value in parse_qsl(parsed.query, keep_blank_values=True)):
        diagnostics.append(ConfigDiagnostic("error", "ai.api_base must not contain credentials in its query string."))
    if parsed.fragment:
        diagnostics.append(ConfigDiagnostic("error", "ai.api_base must not contain a URL fragment."))
    return tuple(diagnostics)


def _validate_ai_bounds(ai: AIConfig) -> tuple[ConfigDiagnostic, ...]:
    diagnostics: list[ConfigDiagnostic] = []
    if not 1.0 <= ai.timeout_seconds <= 600.0:
        diagnostics.append(ConfigDiagnostic("error", "ai.timeout_seconds must be between 1 and 600."))
    if not 0 <= ai.max_retries <= 10:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_retries must be between 0 and 10."))
    if not 1 <= ai.max_output_tokens <= 65536:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_output_tokens must be between 1 and 65536."))
    if not 1024 <= ai.max_context_chars <= 1_000_000:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_context_chars must be between 1024 and 1000000."))
    if not 1 <= ai.max_modules_per_run <= 20:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_modules_per_run must be between 1 and 20."))
    known_stages = {"planning", "scenario_synthesis", "feedback_analysis"}
    if (
        not ai.allowed_stages
        or len(set(ai.allowed_stages)) != len(ai.allowed_stages)
        or not set(ai.allowed_stages) <= known_stages
    ):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "ai.allowed_stages must be a non-empty unique subset of planning, scenario_synthesis, feedback_analysis.",
            )
        )
    if not 0 <= ai.max_repair_attempts <= 2:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_repair_attempts must be between 0 and 2."))
    if ai.fallback != "deterministic":
        diagnostics.append(ConfigDiagnostic("error", 'ai.fallback must be "deterministic".'))
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


def _validate_depth_policy(policy: VerificationDepthPolicy) -> tuple[ConfigDiagnostic, ...]:
    diagnostics: list[ConfigDiagnostic] = []
    if not policy.module.strip() or not policy.subject.strip():
        diagnostics.append(ConfigDiagnostic("error", "Verification depth policy module and subject must not be empty."))
    parameters = dict(policy.parameters)
    allowed = _DEPTH_ALLOWED_PARAMETERS
    if policy.kind not in allowed:
        return (ConfigDiagnostic("error", f"Unsupported verification depth policy kind: {policy.kind}"),)
    unknown = sorted(set(parameters) - allowed[policy.kind])
    if unknown:
        diagnostics.append(
            ConfigDiagnostic("error", f"Unsupported {policy.kind} verification parameters: {', '.join(unknown)}")
        )
    if policy.kind in PERIPHERAL_CONTRACTS:
        _validate_peripheral_depth(policy, parameters, diagnostics)
    elif policy.kind == "reset":
        _validate_reset_depth(policy, parameters, diagnostics)
    elif policy.kind == "memory":
        _validate_memory_depth(policy, parameters, diagnostics)
    elif policy.kind == "formal":
        _validate_formal_depth(policy, parameters, diagnostics)
    else:
        _validate_cdc_depth(policy, parameters, diagnostics)
    return tuple(diagnostics)


def _validate_peripheral_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    contract = PERIPHERAL_CONTRACTS[policy.kind]
    if parameters.get("profile") != contract.profile:
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                f"Invalid {policy.kind} profile for {policy.module}/{policy.subject}; expected {contract.profile}.",
            )
        )
    for name, minimum, maximum in contract.integer_parameters:
        _validate_bounded_integer(parameters, name, minimum, maximum, policy, diagnostics)
    for name, values in contract.enum_parameters:
        if parameters.get(name) not in values:
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid {policy.kind} {name} for {policy.module}/{policy.subject}.")
            )


def _validate_reset_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    for name in ("release_cycles", "min_assert_cycles", "recovery_cycles", "removal_cycles"):
        _validate_bounded_integer(parameters, name, 1, 32, policy, diagnostics)
    _validate_boolean(parameters, "asynchronous_assertion", policy, diagnostics)


def _validate_memory_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    allowed_values = {
        "profile": {None, "bounded_sram"},
        "read_during_write": {None, "read_first", "write_first", "no_change", "undefined"},
        "initialization": {None, "zero", "unconstrained", "file"},
        "arbitration": {None, "round_robin"},
        "protection": {None, "parity", "secded"},
    }
    for name, values in allowed_values.items():
        if parameters.get(name) not in values:
            diagnostics.append(
                ConfigDiagnostic("error", f"Invalid memory {name} policy for {policy.module}/{policy.subject}.")
            )
    _validate_bounded_integer(parameters, "max_latency_cycles", 1, 1024, policy, diagnostics)


def _validate_formal_depth(
    policy: VerificationDepthPolicy,
    parameters: dict[str, str],
    diagnostics: list[ConfigDiagnostic],
) -> None:
    if parameters.get("profile") not in {None, "bounded_response"}:
        diagnostics.append(ConfigDiagnostic("error", f"Invalid formal profile for {policy.module}/{policy.subject}."))
    _validate_bounded_integer(parameters, "max_latency_cycles", 1, 64, policy, diagnostics)
    _validate_boolean(parameters, "assume_trigger_pulse", policy, diagnostics)
    _validate_boolean(parameters, "require_response_causality", policy, diagnostics)
