"""Load and normalize the active physical-design configuration."""

from __future__ import annotations

import math
import tomllib
from dataclasses import replace
from pathlib import Path
from types import UnionType
from typing import Any, get_args, get_origin, get_type_hints

from dv_platform.domain.models import AdapterPluginConfig, AIConfig, CLIConfig, ContextOptimizationConfig, ProductConfig


def normalize_config(config: CLIConfig, base: Path | None = None) -> CLIConfig:
    root = normalize_path(config.repo_root, base or Path.cwd())
    work = normalize_path(config.work_dir, root)
    output = normalize_path(config.output_dir, root)
    return replace(
        config,
        repo_root=root,
        work_dir=work,
        output_dir=output,
        strict=config.strict or config.ci,
        export_roots=tuple(normalize_path(path, root) for path in config.export_roots) or (work, output),
        product=_normalize_product_config(config.product, root),
        ai=_normalize_ai_config(config.ai, root),
    )


def default_config(repo_root: Path) -> CLIConfig:
    root = normalize_path(repo_root, Path.cwd())
    return normalize_config(
        CLIConfig(repo_root=root, work_dir=root / ".dv-platform", output_dir=root / ".dv-platform/exports")
    )


def load_config(path: Path) -> CLIConfig:
    path = path.expanduser().resolve(strict=False)
    data = tomllib.loads(path.read_text(encoding="utf-8"))
    _validate_config_document(data)
    paths, policy, security = (data.get(key, {}) for key in ("paths", "policy", "security"))
    raw = CLIConfig(
        repo_root=Path(paths.get("repo_root", ".")),
        work_dir=Path(paths.get("work_dir", ".dv-platform")),
        output_dir=Path(paths.get("output_dir", ".dv-platform/exports")),
        allow_network=bool(policy.get("allow_network", False)),
        strict=bool(policy.get("strict", False)),
        ci=bool(policy.get("ci", False)),
        adapter_plugins=tuple(AdapterPluginConfig(**plugin) for plugin in data.get("adapter_plugins", ())),
        audit_enabled=bool(security.get("audit_enabled", True)),
        redact_patterns=tuple(str(item) for item in security.get("redact_patterns", ())),
        approved_plugin_publishers=tuple(str(item) for item in security.get("approved_plugin_publishers", ())),
        export_roots=tuple(Path(item) for item in security.get("export_roots", ())),
        secret_provider=str(security.get("secret_provider", "environment")),
        retention_days=int(security.get("retention_days", 30)),
        product=_product_config(data.get("product", {})),
        ai=_ai_config(data.get("ai", {})),
        context_optimization=_context_optimization_config(data.get("context_optimization", {})),
    )
    return normalize_config(raw, base=path.parent)


def _validate_config_document(data: dict[str, Any]) -> None:
    sections = {
        "paths": (CLIConfig, {"repo_root", "work_dir", "output_dir"}),
        "policy": (CLIConfig, {"allow_network", "strict", "ci"}),
        "security": (
            CLIConfig,
            {
                "audit_enabled",
                "redact_patterns",
                "approved_plugin_publishers",
                "export_roots",
                "secret_provider",
                "retention_days",
            },
        ),
        "product": (ProductConfig, None),
        "ai": (AIConfig, None),
        "context_optimization": (ContextOptimizationConfig, None),
    }
    if set(data) - {*sections, "adapter_plugins"}:
        raise ValueError("configuration contains unsupported sections")
    for section, (model, allowed) in sections.items():
        hints = get_type_hints(model)
        if allowed is not None:
            hints = {key: value for key, value in hints.items() if key in allowed}
        if section == "context_optimization":
            hints.update({key: bool for key in ("enabled", "headroom_enabled", "code_graph_enabled")})
        _validate_config_table(data.get(section, {}), hints, section)
    plugins = data.get("adapter_plugins", [])
    if not isinstance(plugins, list):
        raise ValueError("adapter_plugins must be an array of tables")
    for plugin in plugins:
        _validate_config_table(plugin, get_type_hints(AdapterPluginConfig), "adapter_plugins")


def _validate_config_table(value: object, hints: dict[str, Any], section: str) -> None:
    if not isinstance(value, dict) or set(value) - set(hints):
        raise ValueError(f"{section} must be a table containing supported fields")
    for key, item in value.items():
        if not _matches_toml_type(item, hints[key]):
            raise ValueError(f"{section}.{key} has an invalid configuration type")


def _matches_toml_type(value: object, expected: Any) -> bool:
    origin = get_origin(expected)
    if origin is UnionType:
        return any(_matches_toml_type(value, choice) for choice in get_args(expected))
    if origin is tuple:
        return isinstance(value, list) and all(_matches_toml_type(item, get_args(expected)[0]) for item in value)
    if expected is Path:
        return isinstance(value, str)
    if expected is float:
        try:
            return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
        except OverflowError:
            return False
    return type(value) is expected


def normalize_path(path: Path | str, base: Path) -> Path:
    """Return an absolute, user-expanded path without requiring it to exist."""

    candidate = Path(path).expanduser()
    if not candidate.is_absolute():
        candidate = base / candidate
    return candidate.resolve(strict=False)


def _normalize_optional_path(path: Path | None, base: Path) -> Path | None:
    return normalize_path(path, base) if path is not None else None


def _normalize_product_config(config: ProductConfig, base: Path) -> ProductConfig:
    return replace(
        config,
        entitlement_path=_normalize_optional_path(config.entitlement_path, base),
        trust_policy_path=_normalize_optional_path(config.trust_policy_path, base),
        revocation_path=_normalize_optional_path(config.revocation_path, base),
        signoff_trust_policy_path=_normalize_optional_path(config.signoff_trust_policy_path, base),
    )


def _normalize_ai_config(config: AIConfig, base: Path) -> AIConfig:
    return replace(
        config,
        routing_policy_path=_normalize_optional_path(config.routing_policy_path, base),
        routing_trust_root=_normalize_optional_path(config.routing_trust_root, base),
    )


def _product_config(product) -> ProductConfig:
    return ProductConfig(
        organization=_optional_nonempty_string(product.get("organization")),
        entitlement_path=(
            Path(str(product["entitlement_path"])) if product.get("entitlement_path") is not None else None
        ),
        trust_policy_path=(
            Path(str(product["trust_policy_path"])) if product.get("trust_policy_path") is not None else None
        ),
        revocation_path=(Path(str(product["revocation_path"])) if product.get("revocation_path") is not None else None),
        require_enterprise=bool(product.get("require_enterprise", False)),
        required_physical_domains=tuple(str(item) for item in product.get("required_physical_domains", ())),
        signoff_trust_policy_path=(
            Path(product["signoff_trust_policy_path"]) if product.get("signoff_trust_policy_path") is not None else None
        ),
        require_production_signoff=product.get("require_production_signoff", False),
    )


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
        allowed_stages=tuple(str(item) for item in ai.get("allowed_stages", ("physical_design",))),
        max_repair_attempts=int(ai.get("max_repair_attempts", 2)),
        fallback=str(ai.get("fallback", "deterministic")),
        routing_policy_path=(
            Path(str(ai["routing_policy_path"])) if ai.get("routing_policy_path") is not None else None
        ),
        routing_trust_root=(Path(str(ai["routing_trust_root"])) if ai.get("routing_trust_root") is not None else None),
        data_class=str(ai.get("data_class", "internal")),
        destination=str(ai.get("destination", "external")),
    )


def _context_optimization_config(context_optimization) -> ContextOptimizationConfig:
    headroom_mode = context_optimization.get("headroom_mode")
    code_graph_mode = context_optimization.get("code_graph_mode")
    legacy_global = context_optimization.get("enabled")
    _reject_mode_conflict("headroom", headroom_mode, context_optimization.get("headroom_enabled"), legacy_global)
    _reject_mode_conflict("code_graph", code_graph_mode, context_optimization.get("code_graph_enabled"), legacy_global)
    if headroom_mode is None:
        legacy_headroom = context_optimization.get("headroom_enabled", legacy_global)
        headroom_mode = "advisory" if legacy_headroom is True else "off"
    if code_graph_mode is None:
        legacy_code_graph = context_optimization.get("code_graph_enabled", legacy_global)
        code_graph_mode = "advisory" if legacy_code_graph is True else "off"
    return ContextOptimizationConfig(
        headroom_mode=str(headroom_mode),
        code_graph_mode=str(code_graph_mode),
        stages=tuple(str(item) for item in context_optimization.get("stages", ("physical_design",))),
        headroom_endpoint=str(context_optimization.get("headroom_endpoint", "http://127.0.0.1:8787")),
        headroom_timeout_seconds=float(context_optimization.get("headroom_timeout_seconds", 5)),
        code_graph_command=str(context_optimization.get("code_graph_command", "code-review-graph")),
        code_graph_timeout_seconds=float(context_optimization.get("code_graph_timeout_seconds", 10)),
        code_graph_max_context_chars=int(context_optimization.get("code_graph_max_context_chars", 4000)),
        code_graph_detail_level=str(context_optimization.get("code_graph_detail_level", "minimal")),
        code_graph_auto_update=bool(context_optimization.get("code_graph_auto_update", False)),
    )


def _reject_mode_conflict(name: str, mode: object, specific: object, global_enabled: object) -> None:
    """Reject legacy/current combinations that express different activation."""

    if mode is None:
        return
    enabled = specific if specific is not None else global_enabled
    if enabled is not None and bool(enabled) != (str(mode) != "off"):
        raise ValueError(f"context_optimization.{name}_mode contradicts legacy enabled configuration")


def _optional_nonempty_string(value: object) -> str | None:
    if value is None:
        return None
    text = str(value)
    return text if text else None
