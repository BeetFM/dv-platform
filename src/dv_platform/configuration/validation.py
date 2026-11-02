"""Configuration validation for physical execution, provider access, and context tools."""

from __future__ import annotations

import re
import shlex
from urllib.parse import parse_qsl, urlsplit

from dv_platform.configuration.shared import ConfigDiagnostic
from dv_platform.domain.models import AIConfig, CLIConfig


def validate_config(config: CLIConfig) -> tuple[ConfigDiagnostic, ...]:
    diagnostics: list[ConfigDiagnostic] = []
    _validate_product(config, diagnostics)
    _validate_redaction_and_retention(config, diagnostics)
    _validate_plugin_publishers(config, diagnostics)
    diagnostics.extend(validate_ai_config(config.ai, require_model=False))
    diagnostics.extend(validate_context_optimization_config(config.context_optimization))
    for plugin in config.adapter_plugins:
        if plugin.kind not in {"analyzer_runner", "physical_evidence_importer"}:
            diagnostics.append(ConfigDiagnostic("error", f"unsupported physical adapter kind: {plugin.kind}"))
        if plugin.api_version not in {1, 2}:
            diagnostics.append(ConfigDiagnostic("error", "physical adapter api_version must be 1 or 2"))
    return tuple(diagnostics)


def _validate_product(config: CLIConfig, diagnostics: list[ConfigDiagnostic]) -> None:
    product = config.product
    if product.organization is not None and (
        product.organization != product.organization.strip() or len(product.organization) > 256
    ):
        diagnostics.append(ConfigDiagnostic("error", "product.organization must be a bounded non-empty value."))
    if (product.entitlement_path is None) != (product.trust_policy_path is None):
        diagnostics.append(
            ConfigDiagnostic(
                "error", "product.entitlement_path and product.trust_policy_path must be configured together."
            )
        )
    if product.require_enterprise and product.entitlement_path is None:
        diagnostics.append(ConfigDiagnostic("error", "product.require_enterprise requires an entitlement."))
    allowed_physical = {"asic_timing", "asic_power", "asic_memory"}
    if product.require_production_signoff and product.signoff_trust_policy_path is None:
        diagnostics.append(
            ConfigDiagnostic("error", "production sign-off requires a separate signoff_trust_policy_path.")
        )
    if (
        len(set(product.required_physical_domains)) != len(product.required_physical_domains)
        or set(product.required_physical_domains) - allowed_physical
    ):
        diagnostics.append(ConfigDiagnostic("error", "product.required_physical_domains contains invalid values."))


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


def validate_ai_config(ai: AIConfig, require_model: bool = True) -> tuple[ConfigDiagnostic, ...]:
    """Validate the optional AI planner configuration without resolving credentials."""

    diagnostics: list[ConfigDiagnostic] = []
    if require_model and not ai.model.strip():
        diagnostics.append(ConfigDiagnostic("error", "ai.model must be configured for physical-optimize --ai."))
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
    if (ai.routing_policy_path is None) != (ai.routing_trust_root is None):
        diagnostics.append(
            ConfigDiagnostic("error", "ai.routing_policy_path and ai.routing_trust_root must be configured together.")
        )
    if ai.data_class not in {"public", "internal", "confidential", "restricted"}:
        diagnostics.append(ConfigDiagnostic("error", "ai.data_class is invalid."))
    if not ai.destination or ai.destination != ai.destination.strip() or len(ai.destination) > 256:
        diagnostics.append(ConfigDiagnostic("error", "ai.destination must be a bounded non-empty identity."))
    return tuple(diagnostics)


def validate_context_optimization_config(context_optimization) -> tuple[ConfigDiagnostic, ...]:
    """Validate disabled-by-default external context optimizer settings."""

    diagnostics: list[ConfigDiagnostic] = []
    modes = (context_optimization.headroom_mode, context_optimization.code_graph_mode)
    if any(mode not in {"off", "advisory", "required"} for mode in modes):
        diagnostics.append(ConfigDiagnostic("error", "context_optimization modes must be off, advisory, or required."))
    known_stages = {"physical_design", "rtl_optimization"}
    if (
        not context_optimization.stages
        or len(set(context_optimization.stages)) != len(context_optimization.stages)
        or not set(context_optimization.stages) <= known_stages
    ):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "context_optimization.stages must contain only physical_design or rtl_optimization.",
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
    known_stages = {"physical_design", "rtl_optimization"}
    if (
        not ai.allowed_stages
        or len(set(ai.allowed_stages)) != len(ai.allowed_stages)
        or not set(ai.allowed_stages) <= known_stages
    ):
        diagnostics.append(
            ConfigDiagnostic(
                "error",
                "ai.allowed_stages must contain only physical_design or rtl_optimization.",
            )
        )
    if not 0 <= ai.max_repair_attempts <= 2:
        diagnostics.append(ConfigDiagnostic("error", "ai.max_repair_attempts must be between 0 and 2."))
    if ai.fallback != "deterministic":
        diagnostics.append(ConfigDiagnostic("error", 'ai.fallback must be "deterministic".'))
    return tuple(diagnostics)


def _command_is_valid(command: str) -> bool:
    try:
        return bool(shlex.split(command))
    except ValueError:
        return False
