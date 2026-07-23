"""Shared deterministic Jinja rendering."""

from __future__ import annotations

import json
from collections.abc import Mapping

from jinja2 import Environment, PackageLoader, StrictUndefined

from dv_platform.generation.context import build_target_context


def _json_pretty(value: object) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


class TemplateRenderer:
    """Render package-owned templates with strict, deterministic settings."""

    def __init__(self) -> None:
        self._environment = Environment(
            loader=PackageLoader("dv_platform.generation", "templates"),
            # Output is HDL/Python source, never HTML; escaping would corrupt generated artifacts.
            autoescape=False,  # nosec B701
            undefined=StrictUndefined,
            keep_trailing_newline=True,
            lstrip_blocks=False,
            trim_blocks=False,
            newline_sequence="\n",
        )
        self._environment.filters["json_pretty"] = _json_pretty

    def render(self, template_name: str, context: Mapping[str, object]) -> str:
        return self._environment.get_template(template_name).render(dict(context))


_RENDERER = TemplateRenderer()


def render_target(target: str, content: str) -> str:
    """Render one validated target context while retaining the legacy call signature."""

    if not isinstance(content, Mapping):
        raise TypeError("Target templates require a structured render context")
    presentation = dict(content)
    plan = presentation.pop("_plan", None)
    if plan is None:
        raise TypeError("Target render context requires a verification plan")
    context = build_target_context(plan, target, presentation)
    return _RENDERER.render(f"{target}.j2", context)
