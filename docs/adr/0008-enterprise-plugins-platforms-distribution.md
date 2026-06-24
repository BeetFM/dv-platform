# 0008: Enterprise Plugins, Platforms, and Distribution

## Status

Accepted

## Context

Enterprise deployments need customer-specific tools, style guides, simulators,
formal runners, documentation loaders, embedding providers, vector stores, and
report exporters without making the core load arbitrary repository code.

## Decision

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

## Consequences

The plugin model works with internal package indexes and avoids unsafe implicit
code loading. Distribution starts with the format that best fits Python
adapters and enterprise tool integration, while leaving room for containers
where they help CI.
