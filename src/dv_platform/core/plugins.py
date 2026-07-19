"""Versioned entry-point loading for non-generator platform adapters."""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from importlib import metadata
from typing import cast

from dv_platform.core.models import AdapterPluginConfig

ADAPTER_API_VERSION = 1


@dataclass(frozen=True)
class LoadedAdapterPlugin:
    """One explicitly configured and API-compatible adapter plugin."""

    kind: str
    name: str
    api_version: int
    adapter: object


class _EntryPoint:
    name: str
    group: str

    def load(self) -> object:
        raise NotImplementedError


def load_adapter_plugins(
    configured: tuple[AdapterPluginConfig, ...],
    entry_points: object | None = None,
) -> tuple[LoadedAdapterPlugin, ...]:
    """Load only explicitly enabled adapters and enforce their declared API version."""

    if not configured:
        return ()
    discovered = metadata.entry_points() if entry_points is None else entry_points
    loaded: list[LoadedAdapterPlugin] = []
    for plugin in configured:
        group = f"dv_platform.{plugin.kind}"
        candidates = _entry_points_for_group(discovered, group)
        entry_point = next((item for item in candidates if str(item.name) == plugin.name), None)
        if entry_point is None:
            raise LookupError(f"Enabled adapter plugin was not found: {plugin.kind}/{plugin.name}")
        adapter = entry_point.load()
        if isinstance(adapter, type):
            adapter = adapter()
        api_version = getattr(adapter, "api_version", None)
        if api_version != plugin.api_version or api_version != ADAPTER_API_VERSION:
            raise TypeError(
                f"Adapter plugin API mismatch for {plugin.kind}/{plugin.name}: "
                f"configured={plugin.api_version}, provided={api_version}, supported={ADAPTER_API_VERSION}"
            )
        adapter_kind = getattr(adapter, "kind", plugin.kind)
        if adapter_kind != plugin.kind:
            raise TypeError(
                f"Adapter plugin kind mismatch for {plugin.name}: configured={plugin.kind}, provided={adapter_kind}"
            )
        loaded.append(LoadedAdapterPlugin(plugin.kind, plugin.name, api_version, adapter))
    return tuple(loaded)


def _entry_points_for_group(discovered: object, group: str) -> tuple[_EntryPoint, ...]:
    if hasattr(discovered, "select"):
        selected = discovered.select(group=group)
    elif isinstance(discovered, dict):
        selected = discovered.get(group, ())
    elif isinstance(discovered, Iterable):
        selected = tuple(item for item in discovered if getattr(item, "group", None) == group)
    else:
        selected = ()
    return tuple(cast(_EntryPoint, item) for item in selected)
