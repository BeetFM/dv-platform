"""Verification artifact generation backends, loaded on demand."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    "ArtifactWriteResult": ("dv_platform.generators.artifacts", "ArtifactWriteResult"),
    "write_generated_artifacts": ("dv_platform.generators.artifacts", "write_generated_artifacts"),
    "GeneratorBackend": ("dv_platform.generators.base", "GeneratorBackend"),
    "GeneratorRegistry": ("dv_platform.generators.base", "GeneratorRegistry"),
    "load_generator_plugins": ("dv_platform.generators.base", "load_generator_plugins"),
    "ScenarioRendererRegistration": (
        "dv_platform.generators.scenario_registry",
        "ScenarioRendererRegistration",
    ),
    "ScenarioRendererRegistry": ("dv_platform.generators.scenario_registry", "ScenarioRendererRegistry"),
    "SCENARIO_RENDERERS": ("dv_platform.generators.scenario_registry", "SCENARIO_RENDERERS"),
    **{
        name: (f"dv_platform.generators.{module}", name)
        for module, name in (
            ("cocotb", "CocotbGenerator"),
            ("formal", "FormalGenerator"),
            ("systemverilog", "SystemVerilogGenerator"),
            ("uvm", "UvmGenerator"),
            ("verilog", "VerilogGenerator"),
            ("vhdl", "VhdlGenerator"),
        )
    },
}


def __getattr__(name: str) -> Any:
    try:
        module_name, export_name = _EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value


__all__ = [
    "ArtifactWriteResult",
    "CocotbGenerator",
    "FormalGenerator",
    "GeneratorBackend",
    "GeneratorRegistry",
    "ScenarioRendererRegistration",
    "ScenarioRendererRegistry",
    "SCENARIO_RENDERERS",
    "SystemVerilogGenerator",
    "VerilogGenerator",
    "VhdlGenerator",
    "UvmGenerator",
    "load_generator_plugins",
    "write_generated_artifacts",
]
