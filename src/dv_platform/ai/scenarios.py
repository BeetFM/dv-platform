"""Bounded AI selection of existing deterministic scenario templates."""

from __future__ import annotations

import json
from dataclasses import dataclass

from dv_platform.ai.gateway import GatewayResult, LiteLLMGateway
from dv_platform.core.models import VerificationPlan


@dataclass(frozen=True)
class ScenarioTemplateSelection:
    scenario_id: str
    parameters: tuple[tuple[str, str], ...]


def synthesize_scenario_selections(
    gateway: LiteLLMGateway,
    plan: VerificationPlan,
) -> tuple[tuple[ScenarioTemplateSelection, ...], GatewayResult]:
    """Select existing scenarios and their declared parameters without creating source intent."""

    templates = _scenario_templates(plan)
    context = json.dumps(
        {
            "module": plan.module,
            "templates": [
                {"scenario_id": scenario_id, "parameters": parameters}
                for scenario_id, parameters in sorted(templates.items())
            ],
        },
        sort_keys=True,
    )
    parsed: list[ScenarioTemplateSelection] = []
    result = gateway.execute(
        stage="scenario_synthesis",
        system_prompt=(
            "Select and parameterize only supplied deterministic verification scenario templates. "
            "Do not create source, commands, renderers, waivers, checks, or executable claims."
        ),
        user_prompt=context,
        response_schema=_selection_schema(templates),
        context=context,
        validate=_selection_validator(templates, parsed),
    )
    return (tuple(parsed) if result.status == "accepted" else ()), result


def _scenario_templates(plan: VerificationPlan) -> dict[str, dict[str, str]]:
    templates = {}
    for scenario in plan.scenarios:
        parameters: dict[str, str] = {}
        for index, stimulus in enumerate(scenario.stimulus):
            for key, value in stimulus.parameters:
                parameters[f"{index}:{stimulus.kind}:{key}"] = value
        templates[scenario.scenario_id] = parameters
    return templates


def _selection_validator(
    templates: dict[str, dict[str, str]],
    parsed: list[ScenarioTemplateSelection],
):
    def validate(raw: str) -> None:
        parsed.clear()
        payload = json.loads(raw)
        if (
            not isinstance(payload, dict)
            or set(payload) != {"selections"}
            or not isinstance(payload["selections"], list)
        ):
            raise ValueError("scenario synthesis must contain only a selections list")
        seen: set[str] = set()
        for item in payload["selections"]:
            if not isinstance(item, dict) or set(item) != {"scenario_id", "parameters"}:
                raise ValueError("scenario selection has unknown or missing fields")
            scenario_id = item["scenario_id"]
            parameters = item["parameters"]
            if not isinstance(scenario_id, str) or scenario_id not in templates or scenario_id in seen:
                raise ValueError("scenario selection must reference each existing template at most once")
            if not isinstance(parameters, dict) or any(
                not isinstance(key, str) or not isinstance(value, str) or templates[scenario_id].get(key) != value
                for key, value in parameters.items()
            ):
                raise ValueError("scenario parameters must be a subset of declared deterministic template values")
            seen.add(scenario_id)
            parsed.append(ScenarioTemplateSelection(scenario_id, tuple(sorted(parameters.items()))))

    return validate


def _selection_schema(templates: dict[str, dict[str, str]]) -> dict[str, object]:
    return {
        "type": "object",
        "additionalProperties": False,
        "required": ["selections"],
        "properties": {
            "selections": {
                "type": "array",
                "maxItems": len(templates),
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["scenario_id", "parameters"],
                    "properties": {
                        "scenario_id": {"type": "string", "enum": sorted(templates)},
                        "parameters": {"type": "object", "additionalProperties": {"type": "string"}},
                    },
                },
            },
        },
    }


ScenarioTemplateSelection.__module__ = "dv_platform.analysis.ai_scenarios"
__name__ = "dv_platform.analysis.ai_scenarios"
