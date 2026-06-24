# 0001: Local Project Configuration and Generated State

## Status

Accepted

## Context

The platform is intended to run inside client-controlled RTL repositories and
CI workers. Configuration must be reviewable and reproducible, while generated
state must not pollute source control by default.

## Decision

Use TOML for the default project configuration file.

The default project config lives in the client repository root as
`dv-platform.toml`. Generated manifests, caches, logs, retrieval indexes, run
outputs, and other machine state live under the configured work directory.

Interactive and local exploratory runs may discover HDL files by walking the
repository when no RTL file list is configured, but must emit a warning that the
analysis may be incomplete. Strict and CI/CD workflows must treat missing RTL
file lists as an error.

Network use is disabled by default and must be explicit in configuration.

## Consequences

Project configuration can be reviewed and versioned with the RTL repository.
Generated state remains local and disposable. Exploratory use stays convenient,
while CI remains reproducible and stricter.
