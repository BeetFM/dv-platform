# Architecture and Decisions

Document type: consolidated current and historical documentation.

Purpose: System architecture, evidence model, semantic boundaries, adapters, compatibility, and accepted decisions.

Status: current index and preserved source material. Where a historical
section conflicts with current machine evidence, use the authority order in
[Agent and Documentation Governance](agents.md).

Last consolidated: 2026-07-28.

## Source coverage

Every source below is included in full under a stable migration anchor:

- [`docs/architecture/architecture.md`](#source-docsarchitecturearchitecturemd)
- [`docs/architecture/backends-and-output.md`](#source-docsarchitecturebackends-and-outputmd)
- [`docs/architecture/evidence-model.md`](#source-docsarchitectureevidence-modelmd)
- [`docs/architecture/verilator-ast.md`](#source-docsarchitectureverilator-astmd)
- [`docs/architecture/semantic-cross-check.md`](#source-docsarchitecturesemantic-cross-checkmd)
- [`docs/architecture/slang-compatibility-matrix.md`](#source-docsarchitectureslang-compatibility-matrixmd)
- [`docs/architecture/language-semantic-completeness.md`](#source-docsarchitecturelanguage-semantic-completenessmd)
- [`docs/architecture/verification-depth.md`](#source-docsarchitectureverification-depthmd)
- [`docs/architecture/protocol-profiles.md`](#source-docsarchitectureprotocol-profilesmd)
- [`docs/architecture/enterprise-adapters.md`](#source-docsarchitectureenterprise-adaptersmd)
- [`docs/compatibility/contract.md`](#source-docscompatibilitycontractmd)
- [`docs/adr/README.md`](#source-docsadrreadmemd)
- [`docs/adr/0001-local-project-configuration.md`](#source-docsadr0001-local-project-configurationmd)
- [`docs/adr/0002-verilator-xml-evidence.md`](#source-docsadr0002-verilator-xml-evidencemd)
- [`docs/adr/0003-local-first-documentation-retrieval.md`](#source-docsadr0003-local-first-documentation-retrievalmd)
- [`docs/adr/0004-claim-validation-gating.md`](#source-docsadr0004-claim-validation-gatingmd)
- [`docs/adr/0005-sqlite-canonical-stores.md`](#source-docsadr0005-sqlite-canonical-storesmd)
- [`docs/adr/0006-requirements-driven-generation-targets.md`](#source-docsadr0006-requirements-driven-generation-targetsmd)
- [`docs/adr/0007-formal-uvm-backend-boundaries.md`](#source-docsadr0007-formal-uvm-backend-boundariesmd)
- [`docs/adr/0008-enterprise-plugins-platforms-distribution.md`](#source-docsadr0008-enterprise-plugins-platforms-distributionmd)

<a id="source-docsarchitecturearchitecturemd"></a>
## Architecture

Consolidated from `docs/architecture/architecture.md`.

<a id="source-docsarchitecturearchitecturemd--product-boundary"></a>
### Product Boundary

The platform accepts an RTL repository and design documentation, then produces
verification collateral and design feedback. It should support exploratory use
on incomplete designs and stricter use in continuous integration.

The primary deployment target is a local CLI installed inside enterprise
engineering environments. By default, the CLI should read source repositories,
build retrieval indexes, run RTL tools, generate collateral, and store logs
without moving proprietary design material outside the client-controlled
environment.

Inputs:

- RTL sources: SystemVerilog, Verilog, and VHDL.
- Documentation: Markdown, text, PDFs converted to text, specifications, and
  module notes.
- Build metadata: file lists, simulator configuration, defines, include paths,
  constraints, and target top modules.
- Local policy/configuration: allowed tools, output roots, model endpoints,
  retrieval settings, and privacy/export controls.

Outputs:

- Generated cocotb test benches.
- Generated SystemVerilog, UVM, VHDL, and Verilog verification code.
- Formal harnesses, assumptions, assertions, covers, and run scripts.
- Verification plans and coverage intent.
- Design decision reports with module-scoped recommendations.

<a id="source-docsarchitecturearchitecturemd--agent-workflow"></a>
### Agent Workflow

The platform should use agents as specialized workers around a deterministic
core. The core owns data models, provenance, artifact routing, and validation.

1. Repository ingestion
   - Build a source inventory.
   - Detect HDL languages, file lists, packages, include paths, and top modules.
   - Preserve provenance for every source and documentation excerpt.

2. RTL analysis
   - For Verilog/SystemVerilog, invoke Verilator and consume its AST output as
     the primary structural source of truth.
   - Extract module/entity names, elaborated parameters/generics, ports,
     memories, clocks, resets, block-level control domains, interfaces,
     structured child connections, recognized protocols, and hierarchy.
   - Identify observable behaviors from code structure and documentation.

3. Documentation retrieval
   - Chunk design documentation and attach stable source identifiers.
   - Build a local semantic retrieval index for RAG.
   - Retrieve relevant documentation chunks for each module, interface, and
     behavior under analysis.

4. Claim-checking
   - Represent agent conclusions as claims.
   - Check RTL claims against Verilator AST evidence.
   - Check intent claims against retrieved documentation chunks.
   - Mark claims as supported, contradicted, missing evidence, or unchecked.

5. Requirement synthesis
   - Convert retrieved design documentation into structured requirements.
   - Link requirements to modules, interfaces, registers, transactions, and
     error cases.

6. Verification planning
   - Decide which behaviors need simulation tests, formal properties, or both.
   - Emit a plan with target languages, tool assumptions, missing information,
     and expected checks.
   - Attach claim-check and RAG evidence to every planned check.

7. Artifact generation
   - Generate language-specific test benches through backend adapters.
   - Keep generated files traceable to plan items and source requirements.
   - Bind executable files to the exact analyzed RTL input hashes through a
     per-module execution manifest.

8. Execution and feedback
   - Run available simulators/formal tools when configured.
   - Summarize failures, coverage gaps, and regeneration opportunities.
   - Expand generated traces into pass/fail/unexecuted outcomes per mapped
     check ID, then link failures through requirements, claims, behaviors, and
     evidence.

9. Design review
   - Produce per-module and per-submodule design decisions.
   - Classify recommendations by severity, confidence, and affected system
     concern such as timing, reset strategy, CDC, configurability, or area.

<a id="source-docsarchitecturearchitecturemd--core-principles"></a>
### Core Principles

- Python is the orchestration language.
- The enterprise integration surface is a local CLI first, with other
  integrations layered on top.
- Verilator AST evidence is the source of truth for Verilog/SystemVerilog
  structural claims.
- Documentation-derived intent must come through semantic retrieval with
  source-backed chunks.
- Generated HDL should be backend-owned, not hand-assembled in planner code.
- Every artifact should carry provenance back to the requirement or source that
  caused it to exist.
- Executable compilation must consume a validated source manifest rather than
  rediscovering or guessing its input set at run time.
- Agent output must be validated by deterministic checks before writing files.
- Missing design intent should be represented explicitly instead of guessed
  silently.

<a id="source-docsarchitecturearchitecturemd--subsystem-boundaries"></a>
### Subsystem Boundaries

The implementation is organized around an acyclic target architecture:

```text
domain
  <- infrastructure, configuration
  <- rtl, documentation
  <- verification
  <- generation, formal
  <- execution
  <- ai, enterprise
  <- cli
```

`domain` contains the stable records shared across these boundaries.
`infrastructure` owns I/O, path containment, processes, security, sandboxing,
plugins, and tool versions. `rtl` and `documentation` ingest source material;
`verification` constructs deterministic intent; `generation` and `formal`
produce artifacts; and `execution` consumes those artifacts. AI and enterprise
integrations operate through these records and interfaces. CLI code alone
orchestrates an end-to-end command.

The former `agent`, `analysis`, `core`, `generators`, and `run` paths remain
available as compatibility surfaces while implementation ownership is moved.
Existing entry points, import targets, serialized schema versions, and plugin
contracts remain stable throughout that extraction.

<a id="source-docsarchitecturearchitecturemd--three-phase-generation-pipeline"></a>
### Three-Phase Generation Pipeline

1. Ingestion uses the common `HDLFrontend` contract and returns an
   `RTLAnalysisResult`. Verilator remains authoritative for Verilog and
   SystemVerilog; Slang remains an independent semantic cross-check; VHDL keeps
   its GHDL-authoritative normalization and elaboration policy.
2. `RenderContextBuilder` combines normalized RTL facts, a verification plan,
   retrieved documentation, requirements, configuration, and provenance into
   one validated JSON-compatible mapping.
3. `TemplateRenderer` renders package-owned Jinja templates with
   `StrictUndefined`, disabled autoescaping, and deterministic newline and
   whitespace settings. Target-specific semantic decisions remain in Python
   context builders; templates own presentation only.

Repository-local template injection is deliberately unsupported. This keeps
artifact production deterministic and does not expand the plugin trust
boundary.

<a id="source-docsarchitecturearchitecturemd--local-cli"></a>
### Local CLI

The CLI should be suitable for enterprise use:

- Runs inside the client repository or CI worker.
- Accepts explicit source, documentation, output, and configuration paths.
- Supports offline/local model and embedding endpoints when required.
- Keeps generated indexes and artifacts under client-selected output roots.
- Emits machine-readable reports for CI and human-readable summaries for local
  review.
- Avoids hidden network access; network behavior should be configured and
  auditable.

Initial commands:

| Command | Purpose |
| --- | --- |
| `init` | Create a local project configuration file. |
| `index-docs` | Build or refresh the semantic documentation index. |
| `analyze-rtl` | Run RTL ingestion and Verilator AST extraction. |
| `plan` | Generate module verification plans with evidence references. |
| `generate` | Emit selected verification collateral. |
| `run` | Execute configured simulation/formal tools. |
| `coverage` | Import, merge, report, and gate local coverage reports. |
| `review` | Produce design decision reports. |
| `status` | Report schema/tool/pipeline/coverage state and enforce CI policy. |

<a id="source-docsarchitecturearchitecturemd--claim-check-with-verilator-ast"></a>
### Claim-Check With Verilator AST

For Verilog/SystemVerilog, the platform should not rely on approximate text
parsing when a Verilator AST is available. The intended flow is:

1. Invoke Verilator with the enterprise project's include paths, defines, file
   lists, and top module settings.
2. Persist the AST output under the local work directory.
3. Normalize AST nodes into stable internal facts such as modules, ports,
   elaborated parameters, memory shape, original/specialized instances and port
   connections, assignments, always blocks, control domains, recognized
   protocols, assertions, and hierarchy.
4. Convert agent conclusions into `VerificationClaim` records.
5. Resolve each RTL claim to one or more AST-backed `EvidenceRef` records.
6. Block or downgrade generated artifacts whose critical claims are unsupported.

<a id="source-docsarchitecturearchitecturemd--documentation-rag"></a>
### Documentation RAG

Documentation inputs should be handled through semantic retrieval:

1. Load documentation from configured paths.
2. Chunk documents with stable IDs and source offsets.
3. Embed chunks using the configured local or enterprise-approved provider.
4. Store vectors in a local index under the work directory.
5. Retrieve chunks by module, signal, register, interface, behavior, and failure
   mode.
6. Attach retrieved chunk IDs to requirements, verification plans, generated
   artifacts, and design decision reports.

<a id="source-docsarchitecturearchitecturemd--generation-targets"></a>
### Generation Targets

The initial target matrix:

| Target | Purpose |
| --- | --- |
| `cocotb` | Python-driven simulation tests and quick bring-up. |
| `systemverilog` | Native SystemVerilog test benches and assertions. |
| `uvm` | Scalable constrained-random environments and reusable agents. |
| `vhdl` | Native VHDL test benches for VHDL-first projects. |
| `verilog` | Simple legacy-compatible test benches. |
| `formal` | Harnesses, assumptions, assertions, covers, and scripts. |

<a id="source-docsarchitecturearchitecturemd--early-non-goals"></a>
### Early Non-Goals

- Replacing human verification planning.
- Guaranteeing completeness without executable feedback.
- Assuming a single simulator or formal tool.
- Committing to one LLM or agent framework in core data structures.

<a id="source-docsarchitecturebackends-and-outputmd"></a>
## Backends and output layout

Consolidated from `docs/architecture/backends-and-output.md`.

The [capability matrix](verification.md#source-docsqualificationcapability-matrixmd) is authoritative for backend
depth. A generated file is not evidence of executable support. Unsupported
semantics remain explicit plan gaps.

Machine state lives under `<work-dir>`: frontend facts and manifests, retrieval
indexes, plan/revision SQLite stores, run summaries, coverage, review data, and
owner-only audit records. Generated collateral lives under `<output-dir>` by
family, target, and module. Each published module includes provenance and an
execution manifest with input and artifact hashes. Consumers must not infer
support from paths; use schema fields and status policy.

Aggregate `run --all` supports the global `--json` envelope and includes ordered
module results plus the persisted aggregate-summary path. Report adapters may
write only below configured export roots.

<a id="source-docsarchitectureevidence-modelmd"></a>
## Evidence and Claim Model

Consolidated from `docs/architecture/evidence-model.md`.

The platform represents planner, checker, and reviewer conclusions as explicit
claims. Claims are validated before generated collateral depends on them.

<a id="source-docsarchitectureevidence-modelmd--claim-fields"></a>
### Claim Fields

Each `VerificationClaim` records:

- `claim_id`: stable claim identifier within a plan or report
- `scope`: module, interface, or report scope
- `statement`: human-readable claim
- `claim_type`: one of `rtl_structure`, `rtl_behavior`, `documentation_intent`,
  `planned_check`, or `design_recommendation`
- `severity`: `info`, `low`, `medium`, `high`, or `critical`
- `generation_precondition`: whether executable generated behavior depends on
  the claim
- `status`: current validation state
- `evidence_refs`: source-backed evidence references

<a id="source-docsarchitectureevidence-modelmd--statuses"></a>
### Statuses

Claim statuses are:

- `unchecked`: not validated yet
- `supported`: required evidence exists and matches the claim
- `contradicted`: deterministic evidence contradicts the claim
- `missing_evidence`: required evidence is absent or unavailable

Automatic contradiction is reserved for deterministic mismatches. Heuristic
concerns should be represented as warnings, suspected conflicts, or open
questions.

<a id="source-docsarchitectureevidence-modelmd--evidence-references"></a>
### Evidence References

`EvidenceRef` identifies the source backing a claim:

- `kind`: `verilator_ast`, `document_chunk`, `tool_log`, or
  `generated_artifact`
- `source_id`: source artifact path or stable source identifier
- `locator`: platform-owned locator inside the source artifact
- `summary`: optional human-readable summary

Verilator XML locators include fact categories and source locations when
available. Documentation requirement locators use chunk IDs plus exact sentence
offsets, so deduplicated requirements can retain every precise source occurrence.

Executable artifacts add an `ArtifactTrace` layer. Each generated symbol maps
back to stable check IDs and indexes, requirement IDs, RTL behavior IDs, claim
IDs, and evidence refs. Generation rejects executable artifacts without this
mapping. Simulation/formal summaries expand a symbol or property result into an
independent pass/fail/unexecuted outcome for every mapped check ID and retain the
original trace for triage and failed-result feedback.

<a id="source-docsarchitectureevidence-modelmd--checkers"></a>
### Checkers

The current deterministic checkers validate whether a claim has evidence of the
required kind:

- `check_ast_claim`: requires `verilator_ast` evidence
- `check_documentation_claim`: requires `document_chunk` evidence

If matching evidence is present and available, the claim becomes `supported`.
If no required evidence is present or available, the claim becomes
`missing_evidence`. If a source is explicitly marked contradicted, the claim
becomes `contradicted`.

<a id="source-docsarchitectureevidence-modelmd--generation-gating"></a>
### Generation Gating

Generation gating follows ADR-0004:

- Supported claims allow generation.
- Critical unsupported, unchecked, missing, or contradicted claims block.
- Semantic-construct support is evaluated against each requested target; a
  case statement or internal memory may be safe for an exercised black-box
  cocotb/formal path while remaining blocked for an unsupported target.
- Elaborated parameters, control domains, hierarchy connections, and protocol
  channels remain structured plan facts rather than prose-only assumptions.
- High-severity contradicted claims block.
- High-severity missing or unchecked claims warn locally and block in strict or
  CI mode.
- Medium claims warn by default.
- Medium generation preconditions block until supported.
- Low and info claims are annotated by default, except contradicted claims warn.

`gate_generation` returns an aggregate decision containing all validations,
blocked validations, warnings, and whether generation is allowed.

<a id="source-docsarchitectureevidence-modelmd--reports"></a>
### Reports

Claim reports can be emitted as:

- JSON for CI and automation
- Markdown for human review

The current report filenames are `claims.json` and `claims.md` when written via
`write_claim_reports`.

<a id="source-docsarchitectureverilator-astmd"></a>
## Verilator AST Extraction

Consolidated from `docs/architecture/verilator-ast.md`.

Stage 2 uses Verilator XML as the evidence source for Verilog and
SystemVerilog RTL structure.

<a id="source-docsarchitectureverilator-astmd--invocation"></a>
### Invocation

`dv-platform analyze-rtl` builds a Verilator command from the normalized project
configuration and discovered inventory:

```text
<verilator_executable> --xml-only --Mdir <work-dir>/verilator \
  -I<include-path> -D<define> --top-module <top> <rtl-files>
```

`verilator_executable` may be an executable name, path, or command prefix for a
client wrapper. It is parsed as shell-like arguments with `shlex.split`; the CLI
does not invoke a shell.

Before running XML extraction, the platform also invokes:

```text
<verilator_executable> --version
```

The first output line is recorded as the detected Verilator version. Major
version 5 is the current tested compatibility range. Strict analysis rejects an
unparseable version or another major, and `status --policy ci` rejects stored
facts that were not produced by that tested range.

<a id="source-docsarchitectureverilator-astmd--stored-artifacts"></a>
### Stored Artifacts

The current implementation writes:

- raw Verilator XML files under `<work-dir>/verilator/`
- detected version text at `<work-dir>/verilator/verilator-version.txt`
- stdout log at `<work-dir>/logs/verilator.stdout.log`
- stderr log at `<work-dir>/logs/verilator.stderr.log`
- normalized RTL facts at `<work-dir>/rtl-facts/modules.json`
- failure summary at `<work-dir>/runs/analyze-rtl/verilator-failure.json` when
  Verilator returns a non-zero exit code

`analyze-rtl --dry-run` stops after discovery, manifest writing, validation, and
command construction. It does not invoke Verilator.

<a id="source-docsarchitectureverilator-astmd--normalized-facts"></a>
### Normalized Facts

`modules.json` currently contains:

- `schema_version`
- `verilator_version`
- per-module:
  - `name`
  - `ports`
  - `port_details` with direction, width, signedness, packed range, type,
    interface name, modport, interface direction, and source location
  - `type_details` with aggregate members and resolved member dtype, width,
    signedness, packed range, and source location when available
  - `parameters`
  - `parameter_details` with elaborated value, type, width, signedness,
    local-parameter status, and source location
  - `memories` with element width and unpacked depth when resolvable
  - `clocks`
  - `clock_details` with edge, classification source, and evidence
    confidence
  - `resets`
  - `reset_details` with active level, synchronous/asynchronous classification,
    classification source, and evidence
    confidence
  - `semantic_features` with source location, detector confidence, global
    support, and target-specific safe generation targets
  - `instances`
  - `instance_details` with original/elaborated child module identity and
    structured port connection expressions/signal references
  - `continuous_assignments`
  - `procedural_blocks`
  - `procedural_block_details` with normalized expressions, conservative
    patterns, normalized case branches (selector, labels, default status, and
    exclusivity), expression width/signedness/cast metadata, and control-domain
    identity
  - `control_domains` with clock/reset edges, reset polarity, and asynchronous
    reset classification
  - `protocols` for conventional flat ready/valid channels
  - `assertions`
  - `covers`
  - `ast_refs`

Clock and reset detection is intentionally conservative. For common sequential
blocks with multiple sensitivity edges, the normalizer uses the sensitivity
tree and first reset conditional to identify the reset, polarity, and clock.
Name heuristics are retained as a fallback, and each detail records whether it
came from sensitivity evidence or a name heuristic. Inferred controls are
treated as evidence-backed claims by later planning code, not as unquestioned
truth.

<a id="source-docsarchitectureverilator-astmd--evidence-locators"></a>
### Evidence Locators

`ast_refs` point back to the raw XML source artifact. Locators use stable
category/key strings and include legacy `fl` or current `loc` Verilator
source-location attributes when available:

```text
module:simple_counter@a,1,1,15,10
port:simple_counter.clk@a,4,17,4,20
parameter:simple_counter.WIDTH@a,2,19,2,24
instance:simple_counter.u_limit@a,8,5,8,17
```

The module's `source` field is resolved from Verilator's XML file table. The
`source_id` on evidence remains the raw XML file path. The `locator` format is
platform-owned and may be extended with richer XML paths as more fixtures are
added, but it should remain deterministic for unchanged inputs.

<a id="source-docsarchitectureverilator-astmd--current-limitations"></a>
### Current Limitations

The normalizer is broad but conservative. It now records structured expression
trees, procedures, types, memory reads/writes, generate scopes, imports,
specialization-aware hierarchy, control domains, structural CDC paths, and
profile-driven ready/valid or request/ack channels. Semantic feature safety is
evaluated per generation target rather than by a single global allow decision.
It does not yet fully interpret:

- complete SystemVerilog sizing/casting rules across every operator, aggregate,
  interface,
  package-resolution, generate-condition, assertion, and cover semantics;
- parameter sweep matrices, although multiple elaborated specializations retain
  independent deterministic plan identities;
- memory collision, multi-port, byte-enable, initialization, or ECC policy;
- async FIFO, pulse/toggle, reconvergence, multi-bit CDC, or reset-sequencing
  correctness beyond structural signal-flow and synchronizer-chain evidence;
- Verilator-version-specific XML shapes outside the exercised fixtures.

Those should be added fixture by fixture, with raw XML preserved so normalized
facts can be regenerated as the schema becomes richer.

<a id="source-docsarchitecturesemantic-cross-checkmd"></a>
## SystemVerilog semantic cross-checking

Consolidated from `docs/architecture/semantic-cross-check.md`.

Verilator remains authoritative. Slang is an independent cross-checker: its
facts never overwrite or supplement normalized Verilator facts. It affects
trust through explicit comparison results and policy gates.

<a id="source-docsarchitecturesemantic-cross-checkmd--configuration-and-policy"></a>
### Configuration and policy

```toml
[rtl]
verilator_executable = "verilator"
slang_executable = "slang"
semantic_crosscheck = "report" # off | report | required
```

`analyze-rtl` gives both frontends the same files, include directories, defines,
top modules, and parameter overrides. Each parameter-sweep point is executed and
compared independently.

- `off`: Verilator-only compatibility mode.
- `report`: persist issues and continue an exploratory run. Strict and CI runs
  fail on unavailable, incomplete, or disagreeing required capabilities.
- `required`: fail every workflow unless the aggregate result passes.

`plan` and `generate` re-check the latest result when policy is enforcing, so a
failed or missing cross-check cannot be bypassed by using stale Verilator facts.

<a id="source-docsarchitecturesemantic-cross-checkmd--versioned-contract"></a>
### Versioned contract

Schema/API version 2 records:

- run and specialization identity;
- frontend names, versions, commands, and AST artifact paths;
- checked, unsupported, and required capabilities;
- aggregate status and checked modules;
- per-field issues with severity, canonical values, source locations, and
  Verilator/Slang AST evidence references.

Specializations pair by original design unit and canonical non-local parameter
values. Slang `InstanceBody` records are never collapsed by name or insertion
order. Tool IDs, ordering, scalar widths, constants, ranges, and operation names
are removed or canonicalized before comparison.

Capabilities are fail-closed. Capability support describes the normalizer
profile, not whether a particular design happened to contain a fact. All
qualified capabilities are required when cross-checking is enabled; an unknown
node withdraws its affected capability with a source-located reason. This
distinguishes an empty fact set from a mapper that silently dropped facts.

<a id="source-docsarchitecturesemantic-cross-checkmd--semantic-coverage"></a>
### Semantic coverage

The normalized model and comparator cover structural identity, ports,
parameters, specializations, types and aggregate members, interfaces/modports,
instances and connections, assignments, expression trees, branches,
clock/reset domains, structured properties, imports, generate scopes, and
unpacked memories. Expression facts retain width, signedness, packed range,
cast kind, and source location. Property facts retain immediate/concurrent kind,
clocking, disable condition, body, support status, and unsupported temporal
operators.

The Slang mapper is qualified against real Slang 11 JSON for expressions,
wildcard cases, synchronous and asynchronous resets, immediate and concurrent
properties, delays, enum and nested aggregate types, interface arrays and
modports, package imports, parameterized hierarchy, generate loops and
conditions, and synchronous memories. It marks incomplete constructs as
capability gaps. A conservative source inventory retains inactive generate
branches that the elaborated JSON omits. Verilator facts remain the source used
by planning and generation. Unsupported property temporal operators create
critical generation-precondition claims.

<a id="source-docsarchitecturesemantic-cross-checkmd--artifacts"></a>
### Artifacts

Ordinary runs write:

- `.dv-platform/slang/ast.json`;
- command, version, diagnostics, stdout, and stderr under
  `.dv-platform/slang/`;
- `.dv-platform/slang/crosscheck.json` for the point result;
- `.dv-platform/semantic-crosscheck/result.json` for the aggregate.

Sweep artifacts use `.dv-platform/sweeps/<identity>/slang/`. Slang configuration
and detected version participate in the RTL cache fingerprint.

<a id="source-docsarchitecturesemantic-cross-checkmd--qualified-compatibility-profile"></a>
### Qualified compatibility profile

The current strict compatibility window is Verilator major 5 with Slang major
11. Local integration tests skip when Slang is absent. A qualified CI job sets
`DV_PLATFORM_QUALIFIED_SLANG_CI=1`, which makes tool availability and a real
strict CLI cross-check mandatory.

The parsed document is traversed iteratively, and a qualification benchmark
enforces a five-second / 64-MiB budget on the repository's synthetic large-AST
fixture. See [Slang compatibility matrix](#source-docsarchitectureslang-compatibility-matrixmd) for the
expected pass and fail-closed outcomes.

<a id="source-docsarchitectureslang-compatibility-matrixmd"></a>
## Slang compatibility matrix

Consolidated from `docs/architecture/slang-compatibility-matrix.md`.

The qualified semantic cross-check profile is **Verilator 5 / Slang 11** on
Linux x86-64. Hosted quality CI downloads the official Slang 11.0 archive,
verifies SHA-256
`951a170e10e25e54c91565030acfdfc11c3226714ebf225a18ad4166a898d8a4`,
and runs the matrix with `DV_PLATFORM_QUALIFIED_SLANG_CI=1`.

| Fixture profile | Slang normalization | Cross-frontend result |
| --- | --- | --- |
| Empty structural module | Complete | Passes strict comparison |
| Arithmetic, casts, conditional, `casez`, sync/async reset | Complete | Differences in frontend lowering are reported per field |
| Immediate and concurrent assert/cover | Complete | Verilator-lowered or unavailable property structure fails closed |
| Sequence delay (`##`) | Complete in Slang | Verilator 5 rejects compilation; the workflow fails before generation |
| Enum, nested packed structs, package import, interface array, two modports | Complete | Equivalent layouts compare; lowered expressions remain explicit issues |
| Parameterized hierarchy, loop/conditional generate, memories | Complete | Stable hierarchy is retained; unavailable generate conditions remain explicit issues |
| Inactive conditional generate sweep | Retained as `selected=false` | Cannot disappear as a successful empty comparison |

Unknown expression, branch, property, type, hierarchy, or generate nodes
withdraw the affected capability. Because the qualified profile requires every
declared capability, strict/CI and `required` mode reject that run.

<a id="source-docsarchitectureslang-compatibility-matrixmd--qualification-budgets"></a>
### Qualification budgets

The normalizer uses an iterative document walk rather than recursively
materializing a tuple for every subtree. The regression benchmark normalizes a
synthetic AST with more than 10,000 JSON objects under these per-process limits:

- elapsed time below 5 seconds;
- peak Python allocation below 64 MiB.

The fixture is intentionally small enough for ordinary unit CI. Repository-scale
multi-million-node measurements remain a separate system benchmark.

<a id="source-docsarchitecturelanguage-semantic-completenessmd"></a>
## Language semantic completeness

Consolidated from `docs/architecture/language-semantic-completeness.md`.

dv-platform does not claim to implement the IEEE SystemVerilog, Verilog, or VHDL
languages itself. Production semantic authority belongs to an elaborating language
frontend. The `semantic_manifest` adapter imports that frontend's normalized output,
checks it against schema v2, archives the exact manifest and SHA-256 digest, and writes
canonical RTL facts consumed by `dv-platform plan`.

For exploratory VHDL-only projects, the built-in bounded source frontend can
normalize one unambiguous entity/generic/architecture profile without claiming
full IEEE elaboration. Unsupported interface types, architecture binding, and
mixed-language inputs fail closed. Strict language-completeness authority still
requires a complete governed semantic manifest; the bounded frontend does not
replace that contract.

<a id="source-docsarchitecturelanguage-semantic-completenessmd--supported-standards"></a>
### Supported standards

- SystemVerilog: IEEE 1800-2005, 2009, 2012, 2017, and 2023.
- Verilog: IEEE 1364-1995, 2001, and 2005.
- VHDL: IEEE 1076-1987, 1993, 2000, 2002, 2008, and 2019.

The manifest schema is [dvsem-v2.schema.json](../schemas/rtl/dvsem-v2.schema.json).
Each design unit identifies its language, standard, kind, source, normalized facts,
diagnostics, and completeness ledger.

<a id="source-docsarchitecturelanguage-semantic-completenessmd--completeness-contract"></a>
### Completeness contract

Every design unit declares one state for every semantic dimension:

- lexical preprocessing and compilation-unit/library behavior
- design units, declarations, types, expressions, statements, and subprograms
- hierarchy, elaboration, parameters/generics, ports, and generate constructs
- packages/imports, interfaces/modports, and classes/randomization
- assignments, processes, memories, assertions, and functional coverage
- timing/specify semantics, foreign interfaces, attributes/pragmas, and file I/O
- clocks/resets, CDC, and protocol interpretation

Allowed states are `complete`, `partial`, `unsupported`, and `not_applicable`. Strict
import accepts only `complete` and `not_applicable`. Schema v0/v1 manifests migrate to
v2, but every newly introduced dimension becomes `partial`; migration never invents
semantic support.

<a id="source-docsarchitecturelanguage-semantic-completenessmd--import-flow"></a>
### Import flow

Configure the adapter:

```toml
[[adapter_plugins]]
kind = "semantic_importer"
name = "semantic_manifest"
api_version = 1
```

Import and plan:

```console
dv-enterprise --config dv-platform.toml import-semantics --input build/top.dvsem.json --strict
dv-platform --config dv-platform.toml plan --target formal
dv-platform --config dv-platform.toml status --policy ci
```

Unknown fields, unsupported standards/unit kinds, source paths outside the repository,
missing sources, duplicate identities, dangling memory/domain references, invalid safe
CDC chains, malformed recursive expressions, and error diagnostics fail strict import.
The primary CI status includes the semantic completeness result.

<a id="source-docsarchitectureverification-depthmd"></a>
## Verification Depth

Consolidated from `docs/architecture/verification-depth.md`.

The deterministic depth layer converts normalized RTL facts into closure intent
without claiming semantics that the facts do not prove.

<a id="source-docsarchitectureverification-depthmd--executable-depth"></a>
### Executable depth

- Each normalized control domain with a reset receives assertion/release
  reachability intent. The formal harness emits separate reset asserted and
  released covers.
- Each recognized ready/valid or request/acknowledge source receives stability
  assertions and transfer, backpressure, and recovery covers.
- Supported synchronous writes retain address bounds and post-write assertions,
  plus enable and lowest/highest legal address covers.
- Configured synchronous memory collisions emit same-address collision covers
  and `read_first`, `write_first`, or `no_change` assertions. Policies are used
  only when one read and write access expose unambiguous address/data signals in
  the formal clock domain.
- Qualified bounded SRAM policies add a typed full-address simulation scoreboard
  and a bounded formal reference word for byte merging, two-requester round-robin
  arbitration, zero initialization, collision response, and injected parity errors.
- Generated run traces map these executable checks into normalized closure
  points and canonical plan status.

<a id="source-docsarchitectureverification-depthmd--fail-closed-depth"></a>
### Fail-closed depth

- Asynchronous reset release is planned but not executable until the domain
  model proves its release synchronizer.
- Synchronous memory reads are planned but not asserted while collision policy
  and observable read timing are unknown.
- CDC propagation fails closed when internal synchronizer stages are not
  observable. `--cdc-policy bounded` enables a separate finite-depth external
  latency task whose `bounded_pass` result remains an actionable closure gap.
- `--cdc-policy structural` requires every ordered stage to be exposed as a
  formal output and blocks generation unless an unbounded stage-by-stage proof
  can be emitted.
- Linear synchronizers retain their ordered destination-stage signal names.
  Branching or reconvergent paths are not counted as a safe linear chain.
- Unsafe CDC paths remain explicit closure blockers; they are never converted
  into assumptions.

This boundary prevents an easy proof caused by constraining away the behavior
that needs verification.

<a id="source-docsarchitectureverification-depthmd--explicit-policy"></a>
### Explicit policy

Ambiguous intent is configured with versioned `[[verification_depth]]` records:

```toml
[[verification_depth]]
kind = "memory"
module = "stream_buffer"
subject = "storage"
read_during_write = "read_first"
initialization = "unconstrained"

[[verification_depth]]
kind = "cdc"
module = "status_bridge"
subject = "status_toggle"
source_domain = "write"
destination_domain = "read"
structure = "toggle"
output_signal = "status_sync"
min_stages = "2"
max_latency_cycles = "4"
reset_compatible = "true"
```

Supported kinds are `reset`, `memory`, `cdc`, and `formal`. Parameters are validated and
persisted in canonical plans; unknown parameters and invalid bounds fail
configuration. A policy states intended semantics but does not by itself prove
that RTL implements them.

Qualified pulse policies also require `output_signal` and
`pulse_stretch_cycles`; the stretch must be at least the normalized stage count.
Qualified handshake policies require `output_signal`, `ack_input_signal`, and
`ack_output_signal`, and may provide a comma-separated `data_signals` list whose
values are assumed stable while a request is pending. Planning promotes these
policies only when the ordered forward and reverse paths resolve uniquely.

Qualified async-FIFO policies use `structure = "async_fifo"` with the memory as
the policy subject. They require explicit `write_clock`, `write_reset`,
`write_enable`, `write_data`, `write_binary_pointer`, `write_gray_pointer`,
`write_gray_sync`, `full_signal`, and corresponding `read_*` plus
`empty_signal` mappings. Planning cross-checks those names, directions, widths,
memory accesses, domains, power-of-two depth, and both ordered pointer chains
before registering `cdc_async_fifo` as executable.

Qualified reset-domain policies require `clock`, `release_cycles`,
`asynchronous_assertion`, and `ready_signal`; optional `min_assert_cycles`,
`recovery_cycles`, and `removal_cycles` bounds govern the executable scenario.
An ordered domain also supplies `depends_on_reset`, `depends_on_ready`, and
`dependency_sync_signal`. Planning verifies distinct domains, rejects cycles,
and requires an ordered two-stage dependency-ready path before registering
`reset_domain_sequence` as executable.

Qualified bounded SRAM policies use `profile = "bounded_sram"` and require exact
clock/reset/read-port mappings, two complete write requester mappings, declared
`read_during_write`, `initialization = "zero"`, `arbitration = "round_robin"`,
`protection = "parity"`, and fault injection/error outputs. Planning cross-checks
memory shape, synchronous accesses, domain ownership, directions, address/data widths,
byte-lane widths, and unique signal identities before registering
`memory_bounded_sram` as executable.

Qualified formal policies use `profile = "bounded_response"` with exact clock,
reset, trigger, response, and invariant signal mappings. A 1–64-cycle response
bound, trigger-pulse assumption, and response-causality policy are mandatory.
The deterministic formal renderer emits the property-specific assumption,
induction state/design invariants, bounded liveness, and independent
assumption-witness/response/completion covers before registering
`formal_bounded_response` as executable.

<a id="source-docsarchitectureprotocol-profilesmd"></a>
## Protocol Profile Contract

Consolidated from `docs/architecture/protocol-profiles.md`.

Protocol-profile schema v1 is the shared transaction vocabulary for recognition,
planning, generators, coverage, formal properties, result traces, and future UVM
agents. The machine-readable interchange shape is
[protocol-profile-v1.schema.json](../schemas/verification/protocol-profile-v1.schema.json).

The built-in catalog defines bounded profiles for AXI4-Lite, full AXI4,
packet-complete AXI4-Stream, Wishbone B4, Avalon-MM, Avalon-ST, burst-capable
AHB, and non-coherent TileLink UL/UH. Each profile declares endpoint roles,
canonical channel signals and widths, optional sidebands, acceptance and
completion rules, burst/outstanding/timeout bounds, ordering and error policy,
scoreboard keys, required coverage bins, formal properties, result traces, and
intended targets.

Accepted transaction traces use `protocol-trace-v1.schema.json` and can be
reconciled independently with `dv-enterprise verify-protocol-trace --input
TRACE.json`. The shared reference models enforce burst boundaries and lengths,
AXI IDs/last beats, packet framing/routing/masks, Wishbone response exclusivity,
Avalon pending responses, AHB accepted transfers, and TileLink source matching.

Recognition is deterministic and fail-closed. A match requires every mandatory
signal with compatible endpoint directions. Flat canonical signals may share
one explicit prefix. Non-standard names require an explicit one-to-one alias
map. Multiple instances require an explicit instance identity or alias map;
partial and direction-ambiguous signatures are not inferred from approximate
names. SystemVerilog interface/modport facts remain available in normalized RTL
evidence and must be resolved to explicit member aliases before profile binding.

The contract and recognition layer are implemented. This does not qualify the
new broad protocols for execution: their drivers, monitors, reference models,
scoreboards, coverage, formal properties, native benches, result decoders, UVM
agents, mutation matrices, and external-design evidence remain required before
their generation state can advance beyond `unsupported`. Existing bounded
AXI4-Lite, APB4, AHB-Lite, and paired ready/valid qualification is unchanged.

<a id="source-docsarchitectureenterprise-adaptersmd"></a>
## Enterprise adapters

Consolidated from `docs/architecture/enterprise-adapters.md`.

Enterprise adapters connect licensed or remote EDA/ALM systems without loading vendor
libraries into the dv-platform process. Site-owned wrappers execute vendor commands and
write portable result manifests. dv-platform uses no shell, passes only allowlisted
environment variables, confines all outputs to the run directory, bounds and redacts
logs, terminates timed-out process groups, and rejects symlink/path escapes.

<a id="source-docsarchitectureenterprise-adaptersmd--built-in-profiles"></a>
### Built-in profiles

| Adapter | Kind | Profile |
| --- | --- | --- |
| `questa` | `simulator_runner` | Siemens Questa |
| `vcs` | `simulator_runner` | Synopsys VCS |
| `xcelium` | `simulator_runner` | Cadence Xcelium |
| `riviera_pro` | `simulator_runner` | Aldec Riviera-PRO |
| `vivado_xsim` | `simulator_runner` | AMD Vivado Simulator/XSim |
| `jaspergold` | `formal_runner` | Cadence Jasper |
| `vc_formal` | `formal_runner` | Synopsys VC Formal |
| `questa_formal` | `formal_runner` | Siemens Questa Formal |
| `spyglass` | `analyzer_runner` | Synopsys VC SpyGlass lint/CDC/RDC |
| `alint_pro` | `analyzer_runner` | Aldec ALINT-PRO lint/CDC/RDC |
| `ucis_xml` | `coverage_importer` | Accellera UCIS XML |
| `requirements_manifest` | `requirements_importer` | Governed ALM baseline export |

Profiles describe capabilities, executable discovery hints, license-variable names, and
interchange formats. They deliberately do not hard-code vendor switches. Release- and
site-specific commands belong in reviewed farm wrappers.

<a id="source-docsarchitectureenterprise-adaptersmd--normalized-execution-result"></a>
### Normalized execution result

The wrapper receives `DV_PLATFORM_RESULT_PATH` and writes a document conforming to
[enterprise-result-v1.schema.json](../schemas/enterprise/enterprise-result-v1.schema.json). Every
check has a stable canonical plan `check_id`, module, kind, and status. Strict execution
requires at least one check, rejects skipped/unknown states, and reconciles those IDs
through normal coverage closure.

```console
dv-enterprise --config dv-platform.toml run \
  --adapter questa --family simulator --run-id nightly-001 --strict \
  -- /site/bin/run-questa-wrapper --manifest generated/manifest.json

dv-platform --config dv-platform.toml coverage --from-runs --as-of 2026-07-19
dv-platform --config dv-platform.toml status --policy ci
```

Enterprise run summaries emit normalized coverage or formal points. `--from-runs`
discovers them automatically. Missing results, nonzero/passing contradictions, duplicate
check IDs, unknown fields, missing/escaping artifacts, incomplete traceability, and
configured runners without a result all fail the primary CI policy.

<a id="source-docsarchitectureenterprise-adaptersmd--built-in-local-adapter-matrix"></a>
### Built-in local adapter matrix

The same API-v1 entry-point boundary connects `local_documents` and
`ocr_sidecar` document loaders, `local_hash` embeddings, `local_json` vector
storage, `json_manifest` report export, `regex` redaction policy, and `ucis_xml`
coverage import. `index-docs` and planning use the configured document,
embedding, and vector adapters directly. OCR sidecars use
`<document>.<extension>.ocr.txt`; the core never guesses text from image bytes.

<a id="source-docsarchitectureenterprise-adaptersmd--requirements-baselines"></a>
### Requirements baselines

ALM exporters write [requirements-v1.schema.json](../schemas/verification/requirements-v1.schema.json)
with producer, immutable baseline ID, timezone-qualified export time, approval status,
verification method, hierarchy, and stable requirement IDs.

```toml
[[adapter_plugins]]
kind = "requirements_importer"
name = "requirements_manifest"
api_version = 1
```

```console
dv-enterprise --config dv-platform.toml import-requirements \
  --input build/released.dvreq.json --strict
```

Strict import rejects draft requirements, duplicate IDs, missing parents, schema drift,
and ungoverned timestamps. Imported requirements retain baseline evidence and feed
canonical plan checks and claims.

<a id="source-docscompatibilitycontractmd"></a>
## Refactor compatibility contract

Consolidated from `docs/compatibility/contract.md`.

The maximum-simplification refactor is gated by a deterministic compatibility
fingerprint. The contract covers:

- all symbols and callable signatures at the legacy `agent`, `analysis`, `core`,
  `generators`, `run`, CLI, and enterprise module paths;
- dataclass fields and legacy class lookup modules;
- main and enterprise CLI help, invalid-command exit behavior, stdout, and
  stderr;
- console scripts and plugin entry-point targets;
- persisted schema and adapter API versions; and
- paths, kinds, sizes, and SHA-256 hashes for representative artifacts from
  every built-in generation target.

Temporary roots, repository roots, timestamps, UUIDs, revision IDs, and run IDs
are normalized before hashing. The complete normalized manifest can be
inspected without changing the baseline:

```bash
uv run python scripts/checks/compatibility.py --manifest
```

CI and local refactor checkpoints compare against
`qualification/policies/compatibility-baseline-v1.json`:

```bash
uv run python scripts/checks/compatibility.py --check
```

An intentional compatibility change requires an explicit product decision and
review of the full manifest before updating the baseline. Moving implementation
code behind an existing facade must not require a baseline update.

<a id="source-docsadrreadmemd"></a>
## Architecture Decision Records

Consolidated from `docs/adr/README.md`.

This directory records accepted architecture decisions for the DV platform.
Implementation stages should follow these ADRs unless a later ADR supersedes
one explicitly.

<a id="source-docsadrreadmemd--accepted-decisions"></a>
### Accepted Decisions

- [0001: Local Project Configuration and Generated State](#source-docsadr0001-local-project-configurationmd)
- [0002: Verilator XML as RTL Evidence Source](#source-docsadr0002-verilator-xml-evidencemd)
- [0003: Local-First Documentation Retrieval](#source-docsadr0003-local-first-documentation-retrievalmd)
- [0004: Claim Validation and Generation Gating](#source-docsadr0004-claim-validation-gatingmd)
- [0005: SQLite Canonical Stores With Derived Views](#source-docsadr0005-sqlite-canonical-storesmd)
- [0006: Requirements-Driven Generation Targets](#source-docsadr0006-requirements-driven-generation-targetsmd)
- [0007: Formal and UVM Backend Boundaries](#source-docsadr0007-formal-uvm-backend-boundariesmd)
- [0008: Enterprise Plugins, Platforms, and Distribution](#source-docsadr0008-enterprise-plugins-platforms-distributionmd)

<a id="source-docsadr0001-local-project-configurationmd"></a>
## 0001: Local Project Configuration and Generated State

Consolidated from `docs/adr/0001-local-project-configuration.md`.

<a id="source-docsadr0001-local-project-configurationmd--status"></a>
### Status

Accepted

<a id="source-docsadr0001-local-project-configurationmd--context"></a>
### Context

The platform is intended to run inside client-controlled RTL repositories and
CI workers. Configuration must be reviewable and reproducible, while generated
state must not pollute source control by default.

<a id="source-docsadr0001-local-project-configurationmd--decision"></a>
### Decision

Use TOML for the default project configuration file.

The default project config lives in the client repository root as
`dv-platform.toml`. Generated manifests, caches, logs, retrieval indexes, run
outputs, and other machine state live under the configured work directory.

Interactive and local exploratory runs may discover HDL files by walking the
repository when no RTL file list is configured, but must emit a warning that the
analysis may be incomplete. Strict and CI/CD workflows must treat missing RTL
file lists as an error.

Network use is disabled by default and must be explicit in configuration.

<a id="source-docsadr0001-local-project-configurationmd--consequences"></a>
### Consequences

Project configuration can be reviewed and versioned with the RTL repository.
Generated state remains local and disposable. Exploratory use stays convenient,
while CI remains reproducible and stricter.

<a id="source-docsadr0002-verilator-xml-evidencemd"></a>
## 0002: Verilator XML as RTL Evidence Source

Consolidated from `docs/adr/0002-verilator-xml-evidence.md`.

<a id="source-docsadr0002-verilator-xml-evidencemd--status"></a>
### Status

Accepted

<a id="source-docsadr0002-verilator-xml-evidencemd--context"></a>
### Context

For Verilog and SystemVerilog, generated verification collateral must be backed
by structural RTL evidence rather than fragile source-text parsing or unchecked
natural-language analysis.

<a id="source-docsadr0002-verilator-xml-evidencemd--decision"></a>
### Decision

Stage 2 standardizes on Verilator XML output generated with `--xml-only`.

Raw Verilator XML artifacts are persisted under the configured work directory
and treated as source evidence artifacts. The platform writes a separate
normalized RTL facts JSON containing only platform-owned facts required by
planning, claim-checking, and early generators.

The normalized facts must include stable evidence locators back to the raw XML
artifact. The CLI records the detected Verilator version with AST artifacts.
Stage 2 supports a documented minimum Verilator version; version-specific
compatibility adapters are deferred until fixtures show incompatible XML
shapes.

<a id="source-docsadr0002-verilator-xml-evidencemd--consequences"></a>
### Consequences

The raw AST remains available for debugging and re-normalization, while the
platform consumes a smaller stable schema. Multi-version support is evidence
driven instead of speculative.

<a id="source-docsadr0003-local-first-documentation-retrievalmd"></a>
## 0003: Local-First Documentation Retrieval

Consolidated from `docs/adr/0003-local-first-documentation-retrieval.md`.

<a id="source-docsadr0003-local-first-documentation-retrievalmd--status"></a>
### Status

Accepted

<a id="source-docsadr0003-local-first-documentation-retrievalmd--context"></a>
### Context

Design intent comes from proprietary documentation. Retrieval must preserve
source locations, stable chunk IDs, and local execution guarantees while leaving
room for enterprise-approved embedding and vector backends.

<a id="source-docsadr0003-local-first-documentation-retrievalmd--decision"></a>
### Decision

Stage 3 starts with deterministic document loading, stable chunking, and lexical
retrieval as the local fallback. Embedding providers are defined behind an
adapter and must be explicitly configured. Network embedding providers require
`allow_network = true`.

The default vector-store boundary is local and file-backed under the work
directory. The exact persistence format can be chosen during implementation,
but vector-store behavior must remain replaceable behind an adapter.

Large corpora are handled incrementally using stable document IDs, stable chunk
IDs, content hashes, and deterministic stale-chunk removal. Quantized vector
storage, including TurboQuant-style compression, is an adapter-level
optimization deferred until baseline retrieval quality fixtures exist.

<a id="source-docsadr0003-local-first-documentation-retrievalmd--consequences"></a>
### Consequences

The platform can index and retrieve documentation without hidden network
access. Embeddings and vector compression can be added later without changing
the evidence model or chunk identity scheme.

<a id="source-docsadr0004-claim-validation-gatingmd"></a>
## 0004: Claim Validation and Generation Gating

Consolidated from `docs/adr/0004-claim-validation-gating.md`.

<a id="source-docsadr0004-claim-validation-gatingmd--status"></a>
### Status

Accepted

<a id="source-docsadr0004-claim-validation-gatingmd--context"></a>
### Context

Agents and deterministic planners will produce conclusions about RTL structure,
behavior, documentation intent, planned checks, and recommendations. Generated
artifacts must not silently depend on unsupported or contradicted assumptions.

<a id="source-docsadr0004-claim-validation-gatingmd--decision"></a>
### Decision

Critical claims block generation when missing evidence, contradicted, or
unchecked. High-severity contradicted claims block generation. High-severity
missing or unchecked claims warn during local exploratory use and block in
strict or CI mode.

Medium claims warn by default, but may block when they are explicit generation
preconditions. Low and info claims are annotated or warned without blocking by
default.

Claims that directly affect executable generated behavior are generation
preconditions. Critical preconditions must be supported before generation.
Missing documentation intent produces open questions instead of invented
requirements.

Automatic `contradicted` status requires deterministic evidence mismatch.
Heuristic or confidence-based conflicts are represented as warnings, open
questions, or suspected conflicts, and must not automatically block generation
without explicit evidence.

<a id="source-docsadr0004-claim-validation-gatingmd--consequences"></a>
### Consequences

Local exploration remains possible while CI is conservative. The distinction
between deterministic contradiction and heuristic suspicion keeps failures
explainable and reduces false blockers.

<a id="source-docsadr0005-sqlite-canonical-storesmd"></a>
## 0005: SQLite Canonical Stores With Derived Views

Consolidated from `docs/adr/0005-sqlite-canonical-stores.md`.

<a id="source-docsadr0005-sqlite-canonical-storesmd--status"></a>
### Status

Accepted

<a id="source-docsadr0005-sqlite-canonical-storesmd--context"></a>
### Context

Humans should review generated plans and reports in readable formats, but
generators and CI need efficient, queryable, deterministic machine state.

<a id="source-docsadr0005-sqlite-canonical-storesmd--decision"></a>
### Decision

Use SQLite as the canonical machine store for generated verification plans and
design review findings.

Verification plans are stored under `<work-dir>/plans/plans.sqlite`. Derived
Markdown review files are generated under `<work-dir>/plans/modules/`, with an
index view under `<work-dir>/plans/`.

Design review findings are stored under `<work-dir>/review/review.sqlite`.
Markdown is the primary human view. YAML and JSON are exported for CI/CD and
automation: YAML is optimized for human-readable pipeline artifacts and policy
review, while JSON remains the strict machine/API export. SARIF is exported
only for findings that map cleanly to source locations and rule concepts.

All design review findings are retained in SQLite. Low-confidence and
unknown-confidence findings are hidden from default Markdown, YAML, and JSON
reports unless severity is high or critical. Findings without evidence are not
presented as firm recommendations.

Canonical records avoid wall-clock timestamps unless explicitly needed. Input
hashes, schema versions, and tool versions are preferred for reproducibility.

<a id="source-docsadr0005-sqlite-canonical-storesmd--consequences"></a>
### Consequences

Downstream tools get efficient indexed access without parsing prose. Human
review remains readable through derived Markdown. CI can choose YAML or JSON
depending on whether the consumer is a person or strict automation.

<a id="source-docsadr0006-requirements-driven-generation-targetsmd"></a>
## 0006: Requirements-Driven Generation Targets

Consolidated from `docs/adr/0006-requirements-driven-generation-targets.md`.

<a id="source-docsadr0006-requirements-driven-generation-targetsmd--status"></a>
### Status

Accepted

<a id="source-docsadr0006-requirements-driven-generation-targetsmd--context"></a>
### Context

The platform must generate based on client requirements. Cocotb is useful for
early validation, but the architecture must also support SystemVerilog,
standard Verilog, UVM, VHDL, and formal targets.

<a id="source-docsadr0006-requirements-driven-generation-targetsmd--decision"></a>
### Decision

Generation targets are selected from client requirements, verification plans,
and project configuration. Cocotb may be the first implemented simulation
backend because it is fast to validate, but it is not the assumed product
direction.

Simulation generation must support target-specific output roots:
`<output-dir>/simulation/<target>/modules/<module>/`.

Runtime state, logs, temporary build products, and failure summaries live under
`<work-dir>/runs/simulation/<target>/<module>/`.

Simulator configuration is target-specific and project-specific. If no
simulator is configured, `generate` may still emit artifacts, but `run` fails
with an actionable message. Strict and CI mode require explicit simulator
configuration. No global client-project simulator is assumed.

Every generated target/module directory includes a provenance manifest tying
files back to plan IDs, claim IDs, and evidence refs.

<a id="source-docsadr0006-requirements-driven-generation-targetsmd--consequences"></a>
### Consequences

The first backend can be implemented pragmatically without constraining client
target choice. Generated source and runtime state stay separated, and execution
requirements are explicit.

<a id="source-docsadr0007-formal-uvm-backend-boundariesmd"></a>
## 0007: Formal and UVM Backend Boundaries

Consolidated from `docs/adr/0007-formal-uvm-backend-boundaries.md`.

<a id="source-docsadr0007-formal-uvm-backend-boundariesmd--status"></a>
### Status

Accepted

<a id="source-docsadr0007-formal-uvm-backend-boundariesmd--context"></a>
### Context

Formal verification and UVM environments require stronger assumptions than
simple smoke tests. Poorly inferred assumptions or fake transaction models can
create misleading collateral and maintenance debt.

<a id="source-docsadr0007-formal-uvm-backend-boundariesmd--decision"></a>
### Decision

SymbiYosys is the first formal tool adapter for open fixture validation.
Commercial formal tools are added later as adapters. Formal generation emits a
harness, assumptions, assertions/covers, `.sby` configuration, and a provenance
manifest. Client project execution requires explicit formal tool configuration,
and strict/CI mode requires explicit formal tool configuration.

UVM generation starts as an evidence-backed module-level scaffold only when
interface and transaction boundaries are clear. A useful scaffold includes a
package, interface, transaction item when inferable or configured, sequencer,
driver, monitor, scoreboard stub, env, test, top-level harness, compile/run
file list, and provenance manifest.

If transaction semantics are missing, the UVM backend emits a skeletal harness
with open questions instead of pretending a constrained-random environment is
supported. Missing transaction intent blocks advanced UVM generation in
strict/CI mode.

Test bench style customization is declarative config only. Core generators may
support naming, reset conventions, clock defaults, timescale, naming style,
output naming, tool preferences, header/license text, pragmas, and UVM
verbosity defaults. Arbitrary templates and code-snippet injection are not
supported in the core generator initially.

<a id="source-docsadr0007-formal-uvm-backend-boundariesmd--consequences"></a>
### Consequences

Formal and UVM output remain conservative and evidence-backed. Customer-specific
generation is directed toward future plugins or adapters instead of unsafe core
template expansion.

<a id="source-docsadr0008-enterprise-plugins-platforms-distributionmd"></a>
## 0008: Enterprise Plugins, Platforms, and Distribution

Consolidated from `docs/adr/0008-enterprise-plugins-platforms-distribution.md`.

<a id="source-docsadr0008-enterprise-plugins-platforms-distributionmd--status"></a>
### Status

Accepted

<a id="source-docsadr0008-enterprise-plugins-platforms-distributionmd--context"></a>
### Context

Enterprise deployments need customer-specific tools, style guides, simulators,
formal runners, documentation loaders, embedding providers, vector stores, and
report exporters without making the core load arbitrary repository code.

<a id="source-docsadr0008-enterprise-plugins-platforms-distributionmd--decision"></a>
### Decision

Use Python package entry points as the first plugin model. Plugins must be
explicitly enabled in project config. Core defines stable adapter interfaces for
generators, simulator and formal runners, documentation loaders, embedding
providers, vector stores, style profiles, and report exporters.

Do not auto-load arbitrary repository-local executable code by default.
Enterprise-local plugins can be distributed internally as wheels. A restricted
local plugin directory may be considered later only with explicit config.

Linux is the primary supported operating system. macOS is supported for local
development on a best-effort basis. Windows support is through WSL initially;
native Windows is not a Stage 9 target.

Python 3.11 and 3.12 are the initial supported versions. The primary
distribution format is a Python wheel. Optional enterprise container images may
be added later for reproducible CI runners. Standalone binaries are deferred
until pilot feedback shows a concrete need.

<a id="source-docsadr0008-enterprise-plugins-platforms-distributionmd--consequences"></a>
### Consequences

The plugin model works with internal package indexes and avoids unsafe implicit
code loading. Distribution starts with the format that best fits Python
adapters and enterprise tool integration, while leaving room for containers
where they help CI.
