# Security and privacy operations

## Threat model

Repository file lists, include directives, HDL, PDFs/XML, generated code, tool
commands, plugins, model providers, site wrappers, license variables, and export
destinations are untrusted inputs. Primary risks are path or symlink escape,
entity expansion and oversized documents, generated-code execution, executable
plugin import, command/environment injection, secret persistence, model data
disclosure, denial of service, and false verification closure.

The trust boundary is a customer-controlled Linux or WSL runner. Run Veriforge
as an unprivileged dedicated account in an ephemeral container or VM, mount the
RTL repository read-only when practical, place work/output directories on
separate writable volumes, deny outbound network access by default, and expose
only the license variables required by the selected adapter. Native Windows and
macOS are not supported production platforms.

The parser and result boundaries fail closed on unsupported schemas, DTD/entity
XML, malformed checks, unsafe paths, and incomplete traceability. Tool processes
have time, output, concurrency, and memory bounds. This is defense in depth, not
a claim that EDA tools safely process hostile RTL.

## Plugins, secrets, exports, and retention

Built-in entry points ship in the signed Veriforge distribution. Every
third-party adapter or generator must configure an approved publisher, a
SHA-256 digest of its installed distribution, and either a Sigstore bundle
constrained by certificate identity/OIDC issuer or an enterprise-PKI CMS
signature constrained by a trust root. Verification occurs before executable
code is imported.

Plugin API v1 remains supported throughout the 1.x compatibility line. API v2
adds mandatory `sandbox_aware = true` and `audit_schema_version = 1` contracts;
the same signature and identity policy runs before either version is imported.

Secrets are named, never stored in TOML. `security.secret_provider =
"environment"` is the supported provider; AI keys and license variables should
be injected by the isolated runner. Logs and audit records apply configured
redaction patterns, but operators must test organization-specific patterns.

Exports are restricted to `security.export_roots`. The default roots are the
work and generated-output directories. Retain state for
`security.retention_days` (default 30). `purge --as-of YYYY-MM-DD` is a dry run;
add `--apply` only after review. It refuses symlinks and is restricted to
transient AI cache/run, audit, log, RAG-index, and support-bundle trees. Plans,
run evidence, coverage, generated artifacts, and backups are never purge
targets. Network telemetry is disabled by default.

Optional rootless OCI execution uses Podman or Docker with network disabled, a
read-only root, dropped capabilities, no-new-privileges, bounded CPU/memory/PIDs,
an isolated writable run mount, and only explicitly named environment variables.
`execution.license_tokens` caps concurrent runs alongside aggregate-memory limits.

## Incident handling

Follow [SECURITY.md](../SECURITY.md). Preserve content-free digests, affected
versions, configuration shape, and audit records; do not attach proprietary RTL,
documents, raw logs, credentials, or license files to a support ticket.
