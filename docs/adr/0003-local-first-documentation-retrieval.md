# 0003: Local-First Documentation Retrieval

## Status

Accepted

## Context

Design intent comes from proprietary documentation. Retrieval must preserve
source locations, stable chunk IDs, and local execution guarantees while leaving
room for enterprise-approved embedding and vector backends.

## Decision

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

## Consequences

The platform can index and retrieve documentation without hidden network
access. Embeddings and vector compression can be added later without changing
the evidence model or chunk identity scheme.
