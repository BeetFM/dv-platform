"""Authoritative HDL ingestion frontends."""

from importlib import import_module
from typing import Any

from dv_platform.rtl.frontend import HDLFrontend, RTLAnalysisResult

_LAZY_EXPORTS = {
    "SlangFrontend": ("dv_platform.rtl.slang", "SlangFrontend"),
    "VHDLFrontend": ("dv_platform.rtl.vhdl", "VHDLFrontend"),
    "VerilatorFrontend": ("dv_platform.rtl.verilator", "VerilatorFrontend"),
}


def __getattr__(name: str) -> Any:
    try:
        module_name, export_name = _LAZY_EXPORTS[name]
    except KeyError as error:
        raise AttributeError(name) from error
    value = getattr(import_module(module_name), export_name)
    globals()[name] = value
    return value


__all__ = [
    "HDLFrontend",
    "RTLAnalysisResult",
    "SlangFrontend",
    "VHDLFrontend",
    "VerilatorFrontend",
]
