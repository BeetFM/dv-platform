# mypy: disable-error-code=name-defined
# ruff: noqa: F821
"""Local CLI entry point for enterprise RTL verification workflows."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING, cast

from dv_platform.core.models import CLIConfig

if TYPE_CHECKING:
    from dv_platform.analysis.docs import (
        DocumentLoader,
        EmbeddingProvider,
        LocalHashEmbeddingProvider,
        LocalJsonVectorStore,
        VectorStore,
        chunk_documents,
        discover_documentation_files,
        load_documents_with_adapters,
        write_document_index_with_adapters,
    )
    from dv_platform.core.plugins import LoadedAdapterPlugin


def _index_docs(
    args: argparse.Namespace,
    config: CLIConfig,
    loaded_adapters: tuple[LoadedAdapterPlugin, ...] = (),
) -> int:
    try:
        loaders = tuple(
            cast(DocumentLoader, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "document_loader"
        )
        providers = tuple(
            cast(EmbeddingProvider, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "embedding_provider"
        )
        stores = tuple(cast(VectorStore, plugin.adapter) for plugin in loaded_adapters if plugin.kind == "vector_store")
        if len(providers) > 1 or len(stores) > 1:
            raise ValueError("index-docs accepts at most one embedding_provider and one vector_store adapter")
        provider = providers[0] if providers else LocalHashEmbeddingProvider()
        store = stores[0] if stores else LocalJsonVectorStore()
        documentation_files = discover_documentation_files(config.documentation_paths, loaders)
        documents = load_documents_with_adapters(documentation_files, loaders)
        chunks = chunk_documents(documents, max_chars=args.chunk_size)
        index_path = write_document_index_with_adapters(config, chunks, provider, store)
    except (OSError, ValueError) as error:
        _emit_error(args, "index-docs", "index_failed", str(error))
        return 2

    _emit_success(
        args,
        "index-docs",
        {
            "repo_root": str(config.repo_root),
            "documentation_files": len(documentation_files),
            "chunks": len(chunks),
            "index": str(index_path),
            "document_loaders": [plugin.name for plugin in loaded_adapters if plugin.kind == "document_loader"],
            "embedding_provider": getattr(provider, "model", type(provider).__name__),
            "vector_store": type(store).__name__,
        },
        (
            "command=index-docs",
            f"repo_root={config.repo_root}",
            f"documentation_files={len(documentation_files)}",
            f"chunks={len(chunks)}",
            f"index={index_path}",
        ),
    )
    return 0
