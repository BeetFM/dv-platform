"""Configuration loading, normalization, validation, and serialization."""

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dv_platform.configuration.loading import normalize_config
from dv_platform.configuration.parameters import expand_parameter_matrix
from dv_platform.domain.models import (
    CLIConfig,
)
from dv_platform.infrastructure.io import atomic_write_text


def write_config(config: CLIConfig, path: Path) -> None:
    """Write a deterministic TOML config file."""

    config_path = path.expanduser().resolve(strict=False)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    normalized = normalize_config(config, base=config_path.parent)
    matrix_points = set(
        expand_parameter_matrix(
            normalized.parameter_matrix,
            constraints=normalized.parameter_constraints,
            maximum_points=normalized.max_parameter_points,
        )
        if normalized.parameter_matrix
        else ()
    )
    explicit_sweeps = tuple(sweep for sweep in normalized.parameter_sweeps if sweep not in matrix_points)

    text = "\n".join(
        (
            "# dv-platform local project configuration",
            "",
            "[paths]",
            f'repo_root = "{_toml_path(normalized.repo_root, config_path.parent)}"',
            f'work_dir = "{_toml_path(normalized.work_dir, normalized.repo_root)}"',
            f'output_dir = "{_toml_path(normalized.output_dir, normalized.repo_root)}"',
            f"documentation_paths = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.documentation_paths)}",
            f"register_map_paths = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.register_map_paths)}",
            f"rtl_filelists = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.rtl_filelists)}",
            f"include_paths = {_toml_array(_toml_path(path, normalized.repo_root) for path in normalized.include_paths)}",
            "",
            "[rtl]",
            f"defines = {_toml_array(normalized.defines)}",
            f"parameter_overrides = {_toml_array(normalized.parameter_overrides)}",
            f"parameter_sweeps = {_toml_nested_array(explicit_sweeps)}",
            f"parameter_constraints = {_toml_array(normalized.parameter_constraints)}",
            f"max_parameter_points = {normalized.max_parameter_points}",
            *(
                (f'cross_language_bindings = "{_toml_path(normalized.cross_language_bindings, normalized.repo_root)}"',)
                if normalized.cross_language_bindings is not None
                else ()
            ),
            f"top_modules = {_toml_array(normalized.top_modules)}",
            f'verilator_executable = "{_escape(normalized.verilator_executable)}"',
            f'slang_executable = "{_escape(normalized.slang_executable)}"',
            f'semantic_crosscheck = "{_escape(normalized.semantic_crosscheck)}"',
            *(
                ("", "[rtl.parameter_matrix]")
                + tuple(f"{name} = {_toml_array(values)}" for name, values in normalized.parameter_matrix)
                if normalized.parameter_matrix
                else ()
            ),
            "",
            "[retrieval]",
            f'index_dir = "{_toml_path(normalized.retrieval_index_dir or normalized.work_dir / "rag-index", normalized.repo_root)}"',
            "",
            "[policy]",
            f"allow_network = {_toml_bool(normalized.allow_network)}",
            f"strict = {_toml_bool(normalized.strict)}",
            f"ci = {_toml_bool(normalized.ci)}",
            "",
            "[ai]",
            f'model = "{_escape(normalized.ai.model)}"',
            f'api_key_env = "{_escape(normalized.ai.api_key_env or "")}"',
            f'api_base = "{_escape(normalized.ai.api_base or "")}"',
            f'api_version = "{_escape(normalized.ai.api_version or "")}"',
            f"timeout_seconds = {normalized.ai.timeout_seconds:g}",
            f"max_retries = {normalized.ai.max_retries}",
            f"max_output_tokens = {normalized.ai.max_output_tokens}",
            f"max_context_chars = {normalized.ai.max_context_chars}",
            f"max_modules_per_run = {normalized.ai.max_modules_per_run}",
            f"cache = {_toml_bool(normalized.ai.cache)}",
            "allowed_stages = [" + ", ".join(f'"{_escape(stage)}"' for stage in normalized.ai.allowed_stages) + "]",
            f"max_repair_attempts = {normalized.ai.max_repair_attempts}",
            f'fallback = "{_escape(normalized.ai.fallback)}"',
            "",
            "[context_optimization]",
            "stages = ["
            + ", ".join(f'"{_escape(stage)}"' for stage in normalized.context_optimization.stages)
            + "]",
            f'headroom_endpoint = "{_escape(normalized.context_optimization.headroom_endpoint)}"',
            f"headroom_timeout_seconds = {normalized.context_optimization.headroom_timeout_seconds:g}",
            f'code_graph_command = "{_escape(normalized.context_optimization.code_graph_command)}"',
            f"code_graph_timeout_seconds = {normalized.context_optimization.code_graph_timeout_seconds:g}",
            f"code_graph_max_context_chars = {normalized.context_optimization.code_graph_max_context_chars}",
            f'code_graph_detail_level = "{_escape(normalized.context_optimization.code_graph_detail_level)}"',
            f"code_graph_auto_update = {_toml_bool(normalized.context_optimization.code_graph_auto_update)}",
            "",
            "[coverage]",
            *_optional_toml_float("line_minimum", normalized.coverage_policy.line_minimum),
            *_optional_toml_float("branch_minimum", normalized.coverage_policy.branch_minimum),
            *_optional_toml_float("toggle_minimum", normalized.coverage_policy.toggle_minimum),
            *_optional_toml_float("functional_minimum", normalized.coverage_policy.functional_minimum),
            "",
            "[execution]",
            f"max_parallel_modules = {normalized.max_parallel_modules}",
            f"max_process_memory_mb = {normalized.max_process_memory_mb}",
            f"max_total_process_memory_mb = {normalized.max_total_process_memory_mb}",
            f"max_output_bytes = {normalized.max_output_bytes}",
            f"license_tokens = {normalized.license_tokens}",
            f"sandbox_enabled = {str(normalized.sandbox_enabled).lower()}",
            f'sandbox_runtime = "{_escape(normalized.sandbox_runtime)}"',
            *(
                (f'sandbox_image = "{_escape(normalized.sandbox_image)}"',)
                if normalized.sandbox_image is not None
                else ()
            ),
            "sandbox_environment = ["
            + ", ".join(f'"{_escape(item)}"' for item in normalized.sandbox_environment)
            + "]",
            "",
            "[security]",
            f"audit_enabled = {_toml_bool(normalized.audit_enabled)}",
            f"redact_patterns = {_toml_array(normalized.redact_patterns)}",
            f"approved_plugin_publishers = {_toml_array(normalized.approved_plugin_publishers)}",
            f"export_roots = {_toml_array(_toml_path(root, normalized.repo_root) for root in normalized.export_roots)}",
            f'secret_provider = "{_escape(normalized.secret_provider)}"',
            f"retention_days = {normalized.retention_days}",
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
                    *((f'publisher = "{_escape(plugin.publisher)}"',) if plugin.publisher is not None else ()),
                    *(
                        (f'package_sha256 = "{_escape(plugin.package_sha256)}"',)
                        if plugin.package_sha256 is not None
                        else ()
                    ),
                    *((f'signature_kind = "{_escape(plugin.signature_kind)}"',) if plugin.signature_kind else ()),
                    *((f'signature_path = "{_escape(plugin.signature_path)}"',) if plugin.signature_path else ()),
                    *(
                        (f'certificate_identity = "{_escape(plugin.certificate_identity)}"',)
                        if plugin.certificate_identity
                        else ()
                    ),
                    *(
                        (f'certificate_issuer = "{_escape(plugin.certificate_issuer)}"',)
                        if plugin.certificate_issuer
                        else ()
                    ),
                    *((f'trust_root = "{_escape(plugin.trust_root)}"',) if plugin.trust_root else ()),
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
                for binding in normalized.production_protocol_bindings
                for line in (
                    "[[production_protocol_bindings]]",
                    f'profile_id = "{_escape(binding.profile_id)}"',
                    f'module = "{_escape(binding.module)}"',
                    f'instance_id = "{_escape(binding.instance_id)}"',
                    f'role = "{_escape(binding.role)}"',
                    "aliases = { "
                    + ", ".join(f'"{_escape(name)}" = "{_escape(signal)}"' for name, signal in binding.aliases)
                    + " }",
                    "",
                )
            ),
            *(
                line
                for policy in normalized.depth_policies
                for line in (
                    "[[verification_depth]]",
                    f'kind = "{_escape(policy.kind)}"',
                    f'module = "{_escape(policy.module)}"',
                    f'subject = "{_escape(policy.subject)}"',
                    *(f'{name} = "{_escape(value)}"' for name, value in policy.parameters),
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


def _toml_nested_array(values: Iterable[Iterable[object]]) -> str:
    return "[" + ", ".join(_toml_array(value) for value in values) + "]"


def _toml_bool(value: bool) -> str:
    return "true" if value else "false"


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
