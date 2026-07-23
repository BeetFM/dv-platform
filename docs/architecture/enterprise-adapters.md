# Enterprise adapters

Enterprise adapters connect licensed or remote EDA/ALM systems without loading vendor
libraries into the dv-platform process. Site-owned wrappers execute vendor commands and
write portable result manifests. dv-platform uses no shell, passes only allowlisted
environment variables, confines all outputs to the run directory, bounds and redacts
logs, terminates timed-out process groups, and rejects symlink/path escapes.

## Built-in profiles

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

## Normalized execution result

The wrapper receives `DV_PLATFORM_RESULT_PATH` and writes a document conforming to
[enterprise-result-v1.schema.json](../schemas/enterprise-result-v1.schema.json). Every
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

## Built-in local adapter matrix

The same API-v1 entry-point boundary connects `local_documents` and
`ocr_sidecar` document loaders, `local_hash` embeddings, `local_json` vector
storage, `json_manifest` report export, `regex` redaction policy, and `ucis_xml`
coverage import. `index-docs` and planning use the configured document,
embedding, and vector adapters directly. OCR sidecars use
`<document>.<extension>.ocr.txt`; the core never guesses text from image bytes.

## Requirements baselines

ALM exporters write [requirements-v1.schema.json](../schemas/requirements-v1.schema.json)
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
