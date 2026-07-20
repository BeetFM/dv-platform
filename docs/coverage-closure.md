# Coverage Closure

`dv-platform coverage` accepts aggregate LCOV, JSON, and Cobertura metrics. JSON
reports may additionally provide stable coverage points and governed
dispositions. Point-aware reports make closure traceable to verification plan
checks, requirements, and behaviors instead of treating a percentage as proof
that verification intent was exercised.

## Normalized JSON

```json
{
  "modules": {
    "stream_buffer": {
      "line": {"covered": 92, "total": 100},
      "functional": {"covered": 7, "total": 8}
    }
  },
  "coverage_points": [
    {
      "module": "stream_buffer",
      "point_id": "cp:backpressure_stability",
      "kind": "assertion",
      "hits": 1,
      "check_ids": ["check:backpressure_stability"],
      "requirement_ids": ["req:backpressure_stability"]
    },
    {
      "module": "stream_buffer",
      "point_id": "cp:simultaneous_push_pop",
      "kind": "coverpoint",
      "covered": false,
      "check_ids": ["check:simultaneous_push_pop"]
    }
  ]
}
```

`formal_points` is an alias whose default kind is `formal`. Each point requires
`module`, `point_id` (or `id`/`name`), and one of `status`, `covered`, or
`hits`. Supported final states are `covered`, `uncovered`, `bounded_pass`,
`unsupported`, `failed`, `waived`, `unreachable`, and `excluded`.
`bounded_pass` and `unsupported` remain actionable, non-closing states. A failed
executed check remains an actionable gap; execution does not convert a
behavioral failure into coverage closure.

## Dispositions

Dispositions are separate governed records. They never create coverage points
and therefore cannot silently waive a misspelled or stale point ID.

```json
{
  "waivers": [
    {
      "module": "stream_buffer",
      "point_id": "cp:simultaneous_push_pop",
      "disposition_id": "waiver:architecture-17",
      "reason": "The configured single-entry specialization cannot overlap operations.",
      "approved_by": "verification-lead",
      "expires_at": "2027-01-01"
    }
  ],
  "unreachable": [
    {
      "module": "stream_buffer",
      "point_id": "cp:illegal_state",
      "disposition_id": "proof:illegal-state-unreachable",
      "reason": "Inductive invariant excludes the encoded state.",
      "evidence_refs": ["runs/formal/stream_buffer/summary.json#prove"]
    }
  ],
  "exclusions": [
    {
      "module": "stream_buffer",
      "point_id": "cp:debug_only",
      "disposition_id": "exclude:debug-disabled",
      "reason": "Debug logic is not present in this specialization."
    }
  ]
}
```

Waivers require `approved_by`. Unreachable points require evidence. Every
disposition requires a stable ID and reason. Orphaned and conflicting
dispositions reject the import.

## Closure Policy

Raw percentage is covered eligible points divided by all non-excluded points.
Closure percentage additionally counts governed waivers and proven unreachable
points. Exclusions remain visible but are removed from the denominator.

Any active uncovered point fails the coverage command. In strict or CI mode,
traceable functional/formal points without plan mappings and covered points
with stale dispositions also fail. The persisted `closure_gaps` records carry
the IDs needed by the planning feedback stage.

When canonical plans exist, import reconciles each `check_id` with its mapped
points and republishes the plan store with `closure_status` and
`coverage_point_ids`. Executable plan checks without points become
`unmeasured`; point mappings to missing checks become stale. Both conditions
fail point-aware closure and appear as plan open questions so regeneration or
stimulus work cannot silently discard them.

Supported cocotb and formal run summaries emit `coverage_points` or
`formal_points` directly from generated traceability. Those summaries can be
passed back to `dv-platform coverage --input`; point IDs remain bound to stable
check, requirement, and behavior IDs.

## Vendor importers

UCIS and vendor-native databases are loaded through explicitly enabled
`dv_platform.coverage_importer` entry points. An importer implements
`supports(path)` and `import_coverage(path)`, returning this normalized JSON
schema. Core applies the same point, disposition, plan-mapping, and strict/CI
validation after import; a plugin cannot directly mark closure passed.
