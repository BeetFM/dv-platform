"""Evidence-bounded register-map extraction and source conflict handling."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from dv_platform.agent.protocols import RegisterConflict, RegisterField, RegisterModel
from dv_platform.core.models import DocumentationChunk, EvidenceKind, EvidenceRef, RTLModule


@dataclass(frozen=True)
class RegisterAnalysis:
    registers: tuple[RegisterModel, ...]
    conflicts: tuple[RegisterConflict, ...] = ()
    open_questions: tuple[str, ...] = ()


def extract_registers_from_rtl(module: RTLModule) -> tuple[RegisterModel, ...]:
    """Return register facts supplied by a parser/semantic importer without inference."""

    return module.register_models


_REGISTER = re.compile(
    r"\b(?:register\s+)?(?P<name>[A-Za-z_][\w]*)\s+(?:@|offset\s*=)\s*(?P<offset>0x[0-9A-Fa-f]+|\d+)"
    r"(?:\s+width\s*=\s*(?P<width>\d+))?(?:\s+reset\s*=\s*(?P<reset>[^\s]+))?",
    re.IGNORECASE,
)
_FIELD = re.compile(
    r"\b(?:field\s+)?(?P<name>[A-Za-z_][\w]*)\s+\[(?P<msb>\d+)\s*:\s*(?P<lsb>\d+)\]"
    r"(?:\s+access\s*=\s*(?P<access>\w+))?(?:\s+reset\s*=\s*(?P<reset>[^\s]+))?"
    r"(?:\s+side_effect\s*=\s*(?P<side>[^\s]+))?",
    re.IGNORECASE,
)


def extract_registers_from_documentation(
    chunks: tuple[DocumentationChunk, ...], module: str
) -> tuple[RegisterModel, ...]:
    """Parse deliberately narrow, reviewable register notation from documentation."""

    registers: list[RegisterModel] = []
    current: RegisterModel | None = None
    fields: list[RegisterField] = []
    for chunk in chunks:
        if module.lower() not in chunk.text.lower() and module.lower() not in chunk.source.name.lower():
            continue
        for line_number, line in enumerate(chunk.text.splitlines(), start=1):
            register_match = _REGISTER.search(line)
            if register_match:
                if current is not None:
                    registers.append(_replace_fields(current, fields))
                fields = []
                data = register_match.groupdict()
                ref = _doc_ref(chunk, line_number, f"register:{data['name']}")
                current = RegisterModel(
                    name=data["name"],
                    offset=int(data["offset"], 0),
                    width=int(data["width"] or 32),
                    source="documentation",
                    evidence_refs=(ref,),
                )
                continue
            field_match = _FIELD.search(line)
            if field_match and current is not None:
                data = field_match.groupdict()
                fields.append(
                    RegisterField(
                        name=data["name"],
                        msb=int(data["msb"]),
                        lsb=int(data["lsb"]),
                        reset_value=data["reset"],
                        access=data["access"] or "unknown",
                        side_effect=data["side"],
                        reserved=data["name"].lower().startswith("reserved"),
                        evidence_refs=(_doc_ref(chunk, line_number, f"field:{current.name}.{data['name']}"),),
                    )
                )
        if current is not None:
            registers.append(_replace_fields(current, fields))
            current = None
            fields = []
    return _deduplicate_registers(registers)


def load_register_map(path: Path, module: str) -> tuple[RegisterModel, ...]:
    """Load an explicit JSON register map with configuration evidence."""

    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or str(payload.get("module", module)) != module:
        return ()
    registers: list[RegisterModel] = []
    for item in payload.get("registers", ()):
        if not isinstance(item, dict):
            raise ValueError(f"Invalid register entry in {path}")
        evidence = (EvidenceRef(EvidenceKind.CONFIGURATION, str(path), f"register:{item.get('name', 'unknown')}"),)
        fields = tuple(
            RegisterField(
                name=str(field["name"]),
                msb=int(field["msb"]),
                lsb=int(field["lsb"]),
                reset_value=str(field["reset_value"]) if field.get("reset_value") is not None else None,
                access=str(field.get("access", "unknown")),
                side_effect=str(field["side_effect"]) if field.get("side_effect") is not None else None,
                reserved=bool(field.get("reserved", False)),
                evidence_refs=evidence,
            )
            for field in item.get("fields", ())
        )
        registers.append(
            RegisterModel(
                name=str(item["name"]),
                offset=int(item["offset"], 0) if isinstance(item["offset"], str) else item.get("offset"),
                width=int(item.get("width", 32)),
                fields=fields,
                invalid_address_behavior=str(item.get("invalid_address_behavior", "unknown")),
                byte_enable_behavior=str(item.get("byte_enable_behavior", "unknown")),
                source="configuration",
                evidence_refs=evidence,
            )
        )
    return tuple(registers)


def merge_register_sources(
    module: RTLModule,
    sources: tuple[tuple[str, tuple[RegisterModel, ...]], ...],
) -> RegisterAnalysis:
    """Merge equal facts and retain disagreements as explicit conflicts."""

    grouped: dict[str, list[tuple[str, RegisterModel]]] = {}
    for source, registers in sources:
        for register in registers:
            grouped.setdefault(register.name, []).append((source, register))
    accepted: list[RegisterModel] = []
    conflicts: list[RegisterConflict] = []
    questions: list[str] = []
    for name, candidates in sorted(grouped.items()):
        offsets = {str(register.offset) for _source, register in candidates}
        widths = {str(register.width) for _source, register in candidates}
        if len(offsets) > 1:
            refs = tuple(ref for _source, register in candidates for ref in register.evidence_refs)
            conflicts.append(
                RegisterConflict(name, "offset", tuple(sorted(offsets)), "register sources disagree on offset", refs)
            )
            questions.append(f"Resolve conflicting offset evidence for register {module.name}.{name}.")
            continue
        if len(widths) > 1:
            refs = tuple(ref for _source, register in candidates for ref in register.evidence_refs)
            conflicts.append(
                RegisterConflict(name, "width", tuple(sorted(widths)), "register sources disagree on width", refs)
            )
            questions.append(f"Resolve conflicting width evidence for register {module.name}.{name}.")
            continue
        primary = candidates[0][1]
        field_map: dict[str, RegisterField] = {}
        for _source, register in candidates:
            for field in register.fields:
                existing = field_map.get(field.name)
                if existing is not None and (existing.msb, existing.lsb, existing.access) != (
                    field.msb,
                    field.lsb,
                    field.access,
                ):
                    conflicts.append(
                        RegisterConflict(
                            name,
                            f"field:{field.name}",
                            (f"{existing.msb}:{existing.lsb}", f"{field.msb}:{field.lsb}"),
                            "register sources disagree on field",
                            existing.evidence_refs + field.evidence_refs,
                        )
                    )
                    continue
                field_map[field.name] = field
        accepted.append(
            RegisterModel(
                primary.name,
                primary.offset,
                primary.width,
                tuple(field_map.values()),
                primary.invalid_address_behavior,
                primary.byte_enable_behavior,
                "+".join(source for source, _register in candidates),
                tuple(dict.fromkeys(ref for _source, register in candidates for ref in register.evidence_refs)),
            )
        )
    return RegisterAnalysis(tuple(accepted), tuple(conflicts), tuple(dict.fromkeys(questions)))


def _replace_fields(register: RegisterModel, fields: list[RegisterField]) -> RegisterModel:
    return RegisterModel(
        register.name,
        register.offset,
        register.width,
        tuple(fields),
        register.invalid_address_behavior,
        register.byte_enable_behavior,
        register.source,
        register.evidence_refs,
    )


def _deduplicate_registers(registers: list[RegisterModel]) -> tuple[RegisterModel, ...]:
    result: dict[str, RegisterModel] = {}
    for register in registers:
        result[register.name] = register
    return tuple(result.values())


def _doc_ref(chunk: DocumentationChunk, line: int, locator: str) -> EvidenceRef:
    return EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, str(chunk.source), f"{chunk.chunk_id}:{line}:{locator}")
