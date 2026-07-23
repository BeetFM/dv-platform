# RAG operations

Documentation retrieval is local and deterministic by default. Supported text
and extractable PDFs are chunked with source locators and content hashes; local
hash embeddings and a JSON vector index are stored under the configured index
directory. Scanned PDFs require a governed OCR sidecar. Encrypted, malformed,
oversized, or entity-bearing inputs fail closed.

Re-index whenever source content or the embedding implementation changes. Keep
the index with the same confidentiality controls as the source documents, never
publish it as diagnostic data, and purge it under the configured retention
policy. Network embedding/vector providers require explicit adapter enablement
and `allow_network = true`; they are outside the GA contract until separately
qualified.
