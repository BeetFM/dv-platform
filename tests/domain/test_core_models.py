import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from dv_platform.analysis import (
    check_port_claim,
    check_requirement_behavior_claim,
    check_requirement_signal_refs_claim,
    create_initial_plan,
    gate_generation,
)
from dv_platform.analysis.docs import LoadedDocument, chunk_document, write_document_index
from dv_platform.core.config import default_config
from dv_platform.core.models import (
    ClaimStatus,
    ClaimType,
    DocumentationChunk,
    EvidenceKind,
    EvidenceRef,
    RTLModule,
    RTLPort,
    RTLProceduralBlock,
    RTLProceduralPattern,
    RTLProject,
    RTLProtocol,
    RTLSemanticFeature,
    Severity,
    VerificationBehavior,
    VerificationClaim,
    VerificationRequirement,
    VerificationTarget,
)


class CoreModelTests(unittest.TestCase):
    def test_target_specific_semantic_support_does_not_block_safe_target(self) -> None:
        module = RTLModule(
            name="memory_block",
            ports=("clk", "data_o"),
            semantic_features=(
                RTLSemanticFeature(
                    "memory_or_unpacked_array",
                    supported_targets=(VerificationTarget.COCOTB, VerificationTarget.FORMAL),
                ),
            ),
        )

        plan = create_initial_plan(module, (VerificationTarget.COCOTB, VerificationTarget.VHDL))

        self.assertFalse(any(claim.severity == Severity.CRITICAL for claim in plan.claims))
        self.assertTrue(any("unsupported for vhdl" in question for question in plan.open_questions))

    def test_initial_plan_promotes_structured_ready_valid_protocol_checks(self) -> None:
        protocol_ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vstream.xml", "port:stream.in_valid")
        module = RTLModule(
            name="stream",
            ports=("clk", "in_valid", "in_ready", "in_data"),
            port_details=(
                RTLPort("clk", "input", width=1),
                RTLPort("in_valid", "input", width=1),
                RTLPort("in_ready", "output", width=1),
                RTLPort("in_data", "input", width=8),
            ),
            protocols=(
                RTLProtocol(
                    "stream:ready_valid:in",
                    "ready_valid",
                    "in",
                    "sink",
                    "in_valid",
                    "in_ready",
                    "in_data",
                    8,
                    "clk",
                    None,
                    evidence_refs=(protocol_ref,),
                ),
            ),
        )
        text = "The stream accepts a transfer when in_valid and in_ready are asserted."
        chunks = (DocumentationChunk("stream", Path("docs/stream.md"), text, 0, len(text)),)

        plan = create_initial_plan(module, (VerificationTarget.COCOTB,), chunks)

        self.assertEqual(plan.protocols, module.protocols)
        self.assertTrue(any("ready/valid transfers" in check for check in plan.checks))
        planned = next(claim for claim in plan.claims if claim.claim_id.endswith(":planned-check"))
        self.assertEqual(planned.status, ClaimStatus.SUPPORTED)
        self.assertIn(protocol_ref, planned.evidence_refs)

    def test_project_finds_module_by_name(self) -> None:
        module = RTLModule(name="uart_rx")
        project = RTLProject(root=Path("."), modules=[module])

        self.assertEqual(project.module_by_name("uart_rx"), module)
        self.assertIsNone(project.module_by_name("uart_tx"))

    def test_initial_plan_records_clock_reset_and_port_checks(self) -> None:
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n", "data_i", "data_o"),
            clocks=("clk",),
            resets=("rst_n",),
        )

        plan = create_initial_plan(
            module,
            targets=(VerificationTarget.COCOTB, VerificationTarget.FORMAL),
        )

        self.assertEqual(plan.module, "fifo")
        self.assertEqual(plan.targets, (VerificationTarget.COCOTB, VerificationTarget.FORMAL))
        self.assertEqual(tuple(port.name for port in plan.ports), ("clk", "rst_n", "data_i", "data_o"))
        self.assertIn("Drive declared clock inputs with stable periods.", plan.checks)
        self.assertIn("Exercise reset assertion and deassertion sequencing.", plan.checks)
        self.assertIn("Confirm clock classification inferred only from signal naming.", plan.open_questions)
        self.assertIn("Confirm reset polarity and role inferred only from signal naming.", plan.open_questions)

    def test_initial_plan_claims_can_reference_verilator_ast_evidence(self) -> None:
        ast_ref = EvidenceRef(
            kind=EvidenceKind.VERILATOR_AST,
            source_id="verilator:obj_dir/Vtop.xml",
            locator="module:fifo",
            summary="fifo module declaration",
        )
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n"),
            clocks=("clk",),
            resets=("rst_n",),
            ast_refs=(ast_ref,),
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,))

        self.assertEqual(len(plan.claims), 3)
        self.assertTrue(all(claim.status == ClaimStatus.SUPPORTED for claim in plan.claims))
        self.assertTrue(all(claim.evidence_refs == (ast_ref,) for claim in plan.claims))
        self.assertEqual(plan.claims[0].claim_type, ClaimType.RTL_STRUCTURE)
        self.assertEqual(plan.claims[0].severity, Severity.HIGH)
        self.assertTrue(plan.claims[0].generation_precondition)

    def test_port_claim_detects_direction_contradiction(self) -> None:
        ref = EvidenceRef(EvidenceKind.VERILATOR_AST, "Vtop.xml", "port:top.data_o")
        module = RTLModule(
            name="top",
            ports=("data_o",),
            port_details=(RTLPort(name="data_o", direction="output", width=8),),
            ast_refs=(ref,),
        )
        claim = VerificationClaim(
            "top:data_o-input",
            "top",
            "data_o is an input.",
            evidence_refs=(ref,),
        )

        checked = check_port_claim(claim, module, "data_o", direction="input")

        self.assertEqual(checked.status, ClaimStatus.CONTRADICTED)
        self.assertEqual(checked.evidence_refs, (ref,))

    def test_initial_plan_attaches_retrieved_documentation_evidence(self) -> None:
        module = RTLModule(
            name="simple_counter",
            ports=("clk", "rst_n", "enable_i", "count_o"),
            ast_refs=(
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i"),
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o"),
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "procedure:simple_counter.alwaysff"),
            ),
            procedural_block_details=(
                RTLProceduralBlock(
                    kind="alwaysff",
                    patterns=(
                        RTLProceduralPattern(kind="increment", target="count_o", control="enable_i", source="count_o"),
                    ),
                ),
            ),
        )
        chunks = chunk_document(
            LoadedDocument(
                source=Path("docs/counter.md"),
                text="The simple_counter increments count_o when enable_i is asserted.",
            )
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,), documentation_chunks=chunks)

        self.assertEqual(plan.requirements, ("The simple_counter increments count_o when enable_i is asserted.",))
        self.assertEqual(len(plan.structured_requirements), 1)
        requirement_id = plan.structured_requirements[0].requirement_id
        self.assertRegex(requirement_id, r"^simple_counter:docreq:[0-9a-f]{12}$")
        self.assertEqual(plan.structured_requirements[0].scope, "simple_counter")
        self.assertEqual(plan.structured_requirements[0].statement, plan.requirements[0])
        self.assertEqual(plan.structured_requirements[0].evidence_refs[0].kind, EvidenceKind.DOCUMENT_CHUNK)
        documentation_claims = [
            claim for claim in plan.claims if claim.claim_id == "simple_counter:documentation-intent"
        ]
        self.assertEqual(len(documentation_claims), 1)
        self.assertEqual(documentation_claims[0].status, ClaimStatus.SUPPORTED)
        self.assertEqual(documentation_claims[0].claim_type, ClaimType.DOCUMENTATION_INTENT)
        self.assertEqual(documentation_claims[0].evidence_refs[0].kind, EvidenceKind.DOCUMENT_CHUNK)
        self.assertTrue(documentation_claims[0].evidence_refs[0].locator.startswith("chunk:doc:"))
        self.assertIn("Verify count_o increments when enable_i is asserted.", plan.checks)
        planned_claims = [claim for claim in plan.claims if claim.claim_id == f"{requirement_id}:planned-check"]
        self.assertEqual(len(planned_claims), 1)
        self.assertEqual(planned_claims[0].claim_type, ClaimType.PLANNED_CHECK)
        self.assertEqual(planned_claims[0].status, ClaimStatus.SUPPORTED)
        self.assertTrue(any(ref.kind == EvidenceKind.VERILATOR_AST for ref in planned_claims[0].evidence_refs))
        self.assertEqual(
            plan.behaviors,
            (
                VerificationBehavior(
                    behavior_id="simple_counter:behavior:1:1",
                    scope="simple_counter",
                    kind="increment",
                    target="count_o",
                    control="enable_i",
                    source="count_o",
                    evidence_refs=(
                        EvidenceRef(
                            EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "procedure:simple_counter.alwaysff"
                        ),
                    ),
                ),
            ),
        )

    def test_initial_plan_deduplicates_requirements_and_preserves_all_precise_evidence(self) -> None:
        statement = "When enable_i is asserted, count_o increments by one."
        module = RTLModule(
            name="counter",
            ports=("enable_i", "count_o"),
            port_details=(
                RTLPort(name="enable_i", direction="input"),
                RTLPort(name="count_o", direction="output", width=8),
            ),
        )
        chunks = (
            DocumentationChunk("one", Path("docs/a.md"), statement, 10, 10 + len(statement)),
            DocumentationChunk("two", Path("docs/b.md"), statement, 40, 40 + len(statement)),
        )

        plan = create_initial_plan(module, (VerificationTarget.COCOTB,), chunks)

        self.assertEqual(len(plan.structured_requirements), 1)
        requirement = plan.structured_requirements[0]
        self.assertEqual(requirement.category, "increment")
        self.assertEqual(requirement.signals, ("enable_i", "count_o"))
        self.assertEqual(requirement.expected_value, "1")
        self.assertEqual(requirement.confidence, "deterministic")
        self.assertEqual(len(requirement.evidence_refs), 2)
        self.assertEqual(
            tuple(ref.locator for ref in requirement.evidence_refs),
            (f"chunk:one@10:{10 + len(statement)}", f"chunk:two@40:{40 + len(statement)}"),
        )

    def test_initial_plan_blocks_conflicting_requirement_values(self) -> None:
        module = RTLModule(
            name="counter",
            ports=("rst", "data_o"),
            port_details=(
                RTLPort(name="rst", direction="input"),
                RTLPort(name="data_o", direction="output", width=8),
            ),
            resets=("rst",),
        )
        text = "When rst is asserted, data_o resets to zero. When rst is asserted, data_o resets to one."
        chunks = (DocumentationChunk("conflict", Path("docs/counter.md"), text, 0, len(text)),)

        plan = create_initial_plan(module, (VerificationTarget.COCOTB,), chunks)
        gate = gate_generation(plan.claims, strict=True)

        self.assertEqual(len(plan.requirement_conflicts), 1)
        self.assertIn("versus", plan.requirement_conflicts[0].reason)
        self.assertIn("0", plan.requirement_conflicts[0].reason)
        self.assertIn("1", plan.requirement_conflicts[0].reason)
        self.assertFalse(gate.allowed)
        self.assertTrue(any(claim.status == ClaimStatus.CONTRADICTED for claim in plan.claims))
        self.assertTrue(any("Which documented value is authoritative?" in item for item in plan.open_questions))

    def test_structured_tables_timing_performance_power_and_coverage_are_extracted(self) -> None:
        module = RTLModule(
            name="packet_engine",
            ports=("valid", "ready", "status", "sleep"),
            port_details=(
                RTLPort("valid", "input"),
                RTLPort("ready", "output"),
                RTLPort("status", "output", width=32),
                RTLPort("sleep", "input"),
            ),
        )
        text = """# packet_engine revision 2

| Signal | Direction | Width | Requirement |
| --- | --- | --- | --- |
| valid | input | 1 | A transfer shall complete only when ready is high. |

| Register | Offset | Access | Reset | Description |
| --- | --- | --- | --- | --- |
| status | 0x10 | RO | 0 | status reports completion. |

| Metric | Requirement |
| --- | --- |
| Throughput | The packet_engine must sustain at least 2 transactions/cycle. |
| Power | sleep isolation must complete within 3 cycles. |
| Coverage | Coverage must cross valid and ready and reach 100%. |

valid --> ready on the rising edge
"""
        chunks = (DocumentationChunk("structured", Path("docs/packet.md"), text, 0, len(text)),)

        plan = create_initial_plan(module, (VerificationTarget.COCOTB,), chunks)
        categories = {requirement.category for requirement in plan.structured_requirements}
        expected = {requirement.category: requirement.expected_value for requirement in plan.structured_requirements}

        self.assertTrue({"protocol", "register", "performance", "power", "coverage", "timing"} <= categories)
        self.assertEqual(expected["performance"], ">=2 transactions/cycle")
        self.assertEqual(expected["power"], "sleep within 3 cycles")
        self.assertIn(expected["coverage"], {"cross valid x ready", ">=100%"})
        self.assertTrue(all(requirement.evidence_refs for requirement in plan.structured_requirements))

    def test_initial_plan_derives_reset_and_hold_checks_from_requirements(self) -> None:
        module = RTLModule(
            name="simple_counter",
            ports=("clk", "rst_n", "enable_i", "count_o"),
            resets=("rst_n",),
            ast_refs=(
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.rst_n"),
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.enable_i"),
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vsimple_counter.xml", "port:simple_counter.count_o"),
            ),
        )
        chunks = chunk_document(
            LoadedDocument(
                source=Path("docs/counter.md"),
                text=(
                    "The simple_counter reset rst_n clears count_o to zero.\n\n"
                    "The simple_counter holds count_o stable when enable_i is low."
                ),
            ),
            max_chars=80,
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.FORMAL,), documentation_chunks=chunks)

        self.assertIn("Verify rst_n drives count_o to its documented reset value.", plan.checks)
        self.assertIn("Verify count_o remains stable when enable_i is inactive.", plan.checks)

    def test_requirement_signal_refs_claim_is_missing_when_no_known_signals_are_referenced(self) -> None:
        requirement = VerificationRequirement(
            requirement_id="top:docreq:1",
            scope="top",
            statement="The interface asserts packet_done after transfer completion.",
            evidence_refs=(EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/top.md", "chunk:1"),),
        )
        module = RTLModule(name="top", ports=("clk", "valid_i"))
        claim = VerificationClaim(
            "top:docreq:1:planned-check",
            "top",
            "Requirement has planned checks over known RTL signals.",
            evidence_refs=requirement.evidence_refs,
        )

        checked = check_requirement_signal_refs_claim(claim, requirement, module)

        self.assertEqual(checked.status, ClaimStatus.MISSING_EVIDENCE)
        self.assertEqual(checked.evidence_refs, requirement.evidence_refs)

    def test_requirement_behavior_claim_requires_matching_pattern_for_increment(self) -> None:
        requirement = VerificationRequirement(
            requirement_id="counter:docreq:1",
            scope="counter",
            statement="The counter increments count_o when enable_i is asserted.",
            evidence_refs=(EvidenceRef(EvidenceKind.DOCUMENT_CHUNK, "docs/counter.md", "chunk:1"),),
        )
        module = RTLModule(
            name="counter",
            ports=("enable_i", "count_o"),
            ast_refs=(
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcounter.xml", "port:counter.enable_i"),
                EvidenceRef(EvidenceKind.VERILATOR_AST, "Vcounter.xml", "port:counter.count_o"),
            ),
        )
        claim = VerificationClaim(
            "counter:docreq:1:planned-check",
            "counter",
            "Requirement has planned checks over known RTL signals.",
            evidence_refs=requirement.evidence_refs,
        )

        checked = check_requirement_behavior_claim(claim, requirement, module)

        self.assertEqual(checked.status, ClaimStatus.MISSING_EVIDENCE)
        self.assertEqual(checked.evidence_refs, requirement.evidence_refs)

    def test_initial_plan_can_use_configured_vector_retrieval_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            module = RTLModule(
                name="simple_counter",
                ports=("clk", "rst_n", "enable_i", "count_o"),
            )
            chunks = chunk_document(
                LoadedDocument(
                    source=repo / "docs" / "counter.md",
                    text="The simple_counter increments count_o when enable_i is asserted.",
                )
            )
            index_dir = config.retrieval_index_dir or config.work_dir / "rag-index"
            write_document_index(config, chunks)

            plan = create_initial_plan(
                module,
                targets=(VerificationTarget.COCOTB,),
                documentation_chunks=chunks,
                retrieval_index_dir=index_dir,
            )

            self.assertEqual(plan.requirements, ("The simple_counter increments count_o when enable_i is asserted.",))
            self.assertEqual(len(plan.structured_requirements), 1)

    def test_initial_plan_records_open_question_when_documentation_does_not_match(self) -> None:
        module = RTLModule(name="uart_rx", ports=("clk", "data_i"))
        chunks = chunk_document(
            LoadedDocument(
                source=Path("docs/counter.md"),
                text="The counter increments when enable is asserted.",
            )
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,), documentation_chunks=chunks)

        self.assertIn("No documentation intent was retrieved for this module.", plan.open_questions)

    def test_initial_plan_claims_can_gate_generation(self) -> None:
        module = RTLModule(
            name="fifo",
            ports=("clk", "rst_n"),
            clocks=("clk",),
            resets=("rst_n",),
        )

        plan = create_initial_plan(module, targets=(VerificationTarget.COCOTB,))
        gate = gate_generation(plan.claims, strict=True)

        self.assertFalse(gate.allowed)
        self.assertTrue(any(validation.claim.claim_id == "fifo:clocking" for validation in gate.blocked))


if __name__ == "__main__":
    unittest.main()
