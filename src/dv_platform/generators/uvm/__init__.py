"""UVM generator backend."""

# ruff: noqa: F401

from __future__ import annotations

from collections.abc import Iterable
from pathlib import Path

from dv_platform.agent.protocols import ProtocolModel, RegisterField, RegisterModel
from dv_platform.core.literals import sv_numeric_literal_to_int
from dv_platform.core.models import (
    ArtifactKind,
    ArtifactQualityRequirement,
    EvidenceRef,
    GeneratedArtifact,
    RTLProtocol,
    VerificationPlan,
    VerificationTarget,
)
from dv_platform.generation.rendering import render_target
from dv_platform.generators.signals import (
    artifact_trace,
    port_by_name,
    port_names,
    primary_clock_name,
    primary_reset,
    protocol_mapping_header,
    provenance_refs,
    structured_quality_requirements,
    sv_parameter_clause,
)
from dv_platform.generators.uvm_common import (
    _clock_name,
    _comma_terminate,
    _connections,
    _paired_protocol,
    _port_names_from_plan,
    _safe_identifier,
    _unique_refs,
)
from dv_platform.generators.uvm_profiles import (
    _package_content,
    _profile_covergroup_lines,
    _profile_uvm_agent_lines,
    _profile_uvm_handshake,
    _profile_uvm_package_content,
    _profile_uvm_presentation,
    _uvm_field_configuration,
    _uvm_ral_lines,
    _uvm_transaction_fields,
)
from dv_platform.generators.uvm_protocol import (
    _protocol_package_content,
    _protocol_uvm_presentation,
    _uvm_register_build_lines,
)


class UvmGenerator:
    """Generate conservative UVM scaffold artifacts without inventing transactions."""

    target = VerificationTarget.UVM

    def generate(self, plan: VerificationPlan) -> list[GeneratedArtifact]:
        module_name = _safe_identifier(plan.module)
        refs = provenance_refs(plan)
        quality = structured_quality_requirements(plan, "UVM")
        if plan.protocol_models or plan.register_models:
            qualified_ready_valid = _paired_protocol(plan) is not None and not plan.register_models
            quality = (
                *quality,
                ArtifactQualityRequirement(
                    "uvm_vendor_profile_qualified",
                    "Protocol/register UVM generation requires a vendor-qualified deterministic profile.",
                    qualified_ready_valid,
                    None
                    if qualified_ready_valid
                    else "only the paired ready/valid UVM 1.2 profile is vendor-qualified",
                ),
            )
        header = protocol_mapping_header(plan, self.target)
        package_presentation, interface_presentation, top_presentation, readme_presentation = (
            self._presentation_contexts(plan, header)
        )
        return self._render_artifacts(
            plan,
            module_name,
            refs,
            quality,
            (package_presentation, interface_presentation, top_presentation, readme_presentation),
        )

    @staticmethod
    def _render_artifacts(
        plan: VerificationPlan,
        module_name: str,
        refs: tuple[EvidenceRef, ...],
        quality: tuple[ArtifactQualityRequirement, ...],
        presentations: tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]],
    ) -> list[GeneratedArtifact]:
        package_presentation, interface_presentation, top_presentation, readme_presentation = presentations
        return [
            GeneratedArtifact(
                path=Path(f"{module_name}_pkg.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.UVM,
                content=render_target("uvm", package_presentation),  # type: ignore[arg-type]
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"{module_name}_test", target=VerificationTarget.UVM),
            ),
            GeneratedArtifact(
                path=Path(f"{module_name}_if.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.UVM,
                content=render_target("uvm", interface_presentation),  # type: ignore[arg-type]
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"{module_name}_if", target=VerificationTarget.UVM),
            ),
            GeneratedArtifact(
                path=Path(f"tb_{module_name}_uvm.sv"),
                kind=ArtifactKind.TESTBENCH,
                target=VerificationTarget.UVM,
                content=render_target("uvm", top_presentation),  # type: ignore[arg-type]
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
                quality_requirements=quality,
                traceability=artifact_trace(plan, f"tb_{module_name}_uvm", target=VerificationTarget.UVM),
            ),
            GeneratedArtifact(
                path=Path("README.md"),
                kind=ArtifactKind.REPORT,
                target=VerificationTarget.UVM,
                content=render_target("uvm", readme_presentation),  # type: ignore[arg-type]
                source_plan_module=plan.module,
                design_unit=plan.design_unit or plan.module,
                elaborated_design_unit=plan.elaborated_design_unit,
                specialization_id=plan.specialization_id,
                elaborated_parameters=plan.parameters,
                provenance_refs=refs,
            ),
        ]

    @staticmethod
    def _presentation_contexts(
        plan: VerificationPlan,
        header: str,
    ) -> tuple[dict[str, object], dict[str, object], dict[str, object], dict[str, object]]:
        module_name = _safe_identifier(plan.module)
        ports = port_names(plan)
        clock_name = primary_clock_name(plan, ports) or "clk"
        pair = _paired_protocol(plan)
        package = _package_presentation(plan, module_name, pair)
        interface_ports = []
        for name in ports:
            if name == clock_name:
                continue
            detail = port_by_name(plan, name)
            interface_ports.append(
                {
                    "name": name,
                    "width": detail.width if detail is not None else None,
                    "signed": bool(detail is not None and detail.signed),
                }
            )
        interface: dict[str, object] = {
            "artifact_kind": "interface",
            "module": plan.module,
            "module_name": module_name,
            "clock_name": clock_name,
            "ports": interface_ports,
        }
        top: dict[str, object] = {
            "artifact_kind": "top",
            "module": plan.module,
            "module_name": module_name,
            "clock_name": clock_name,
            "design_unit": plan.design_unit or plan.module,
            "parameter_clause": sv_parameter_clause(plan),
            "connections": tuple(
                {
                    "port": name,
                    "signal": clock_name if name == clock_name else "vif." + name,
                }
                for name in ports
            ),
        }
        readme: dict[str, object] = {
            "artifact_kind": "readme",
            "module": plan.module,
            "paired": pair is not None,
            "sink": ({"name": pair[0].name, "profile": pair[0].profile} if pair is not None else None),
            "source": ({"name": pair[1].name, "profile": pair[1].profile} if pair is not None else None),
            "requirements": plan.requirements,
        }
        presentations = package, interface, top, readme
        for presentation in presentations:
            presentation["_plan"] = plan
            presentation["protocol_header"] = header
        return presentations


def _interface_content(plan: VerificationPlan) -> str:
    presentation = UvmGenerator._presentation_contexts(plan, "")[1]
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _top_content(plan: VerificationPlan) -> str:
    presentation = UvmGenerator._presentation_contexts(plan, "")[2]
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _readme_content(plan: VerificationPlan) -> str:
    presentation = UvmGenerator._presentation_contexts(plan, "")[3]
    return render_target("uvm", presentation)  # type: ignore[arg-type]


def _package_presentation(
    plan: VerificationPlan,
    module_name: str,
    pair: tuple[RTLProtocol, RTLProtocol] | None,
) -> dict[str, object]:
    if pair is None:
        if any(model.profile_id and model.profile_id.endswith("-1.0") for model in plan.protocol_models):
            return _profile_uvm_presentation(plan, module_name)
        return {
            "artifact_kind": "scaffold_package",
            "module": plan.module,
            "module_name": module_name,
        }
    return _protocol_uvm_presentation(plan, module_name, *pair)
