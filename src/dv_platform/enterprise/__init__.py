"""Enterprise semantic and tool adapter contracts, loaded on demand."""

from importlib import import_module
from typing import Any

_EXPORTS = {
    name: ("dv_platform.enterprise.semantics", name)
    for name in ("SemanticDiagnostic", "SemanticImportError", "SemanticImportResult", "SemanticManifestImporter")
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
    "SemanticDiagnostic",
    "SemanticImportError",
    "SemanticImportResult",
    "SemanticManifestImporter",
]
