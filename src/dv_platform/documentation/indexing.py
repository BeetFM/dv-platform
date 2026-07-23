"""Local documentation loading, chunking, and retrieval helpers."""

from __future__ import annotations

import hashlib
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, DocumentationChunk

SUPPORTED_DOCUMENT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".pdf"}
SKIPPED_DOCUMENT_DIRECTORIES = {".git", ".hg", ".svn", ".dv-platform", "__pycache__"}
DOCUMENT_INDEX_SCHEMA_VERSION = 2
VECTOR_INDEX_SCHEMA_VERSION = 1
MAX_DOCUMENT_BYTES = 64 * 1024 * 1024
MAX_PDF_PAGES = 10_000
MAX_EXTRACTED_TEXT_CHARACTERS = 64 * 1024 * 1024


@dataclass(frozen=True)
class LoadedDocument:
    """A local documentation file loaded for indexing."""

    source: Path
    text: str
    page_ranges: tuple[tuple[int, int, int], ...] = ()


@dataclass(frozen=True)
class RetrievalResult:
    """A lexical retrieval hit from the local documentation index."""

    chunk: DocumentationChunk
    score: float
    matched_terms: tuple[str, ...]


class EmbeddingProvider(Protocol):
    """Adapter boundary for documentation embedding providers."""

    model: str
    dimensions: int

    def embed_text(self, text: str) -> tuple[float, ...]:
        """Return one normalized embedding vector for text."""


class DocumentationRetriever(Protocol):
    """Adapter boundary for documentation retrieval implementations."""

    def retrieve(
        self,
        query: str,
        chunks: tuple[DocumentationChunk, ...],
        limit: int = 5,
    ) -> tuple[RetrievalResult, ...]:
        """Return ranked retrieval results for a query."""


class DocumentLoader(Protocol):
    """Versioned loader boundary for text, PDF, or OCR-derived documents."""

    def supports(self, path: Path) -> bool: ...

    def load(self, path: Path) -> LoadedDocument: ...


class VectorStore(Protocol):
    """Persistent vector-store adapter used by indexing and retrieval."""

    def write(
        self,
        index_dir: Path,
        chunks: tuple[DocumentationChunk, ...],
        provider: EmbeddingProvider,
    ) -> Path: ...

    def read(self, index_dir: Path) -> VectorIndex: ...


@dataclass(frozen=True)
class VectorRecord:
    """Persisted local vector for one documentation chunk."""

    chunk_id: str
    content_hash: str | None
    embedding: tuple[float, ...]


@dataclass(frozen=True)
class VectorIndex:
    """Local file-backed vector index content."""

    schema_version: int
    embedding_model: str
    dimensions: int
    records: tuple[VectorRecord, ...]


class LexicalRetriever:
    """Deterministic lexical retriever used as the local fallback."""

    def retrieve(
        self,
        query: str,
        chunks: tuple[DocumentationChunk, ...],
        limit: int = 5,
    ) -> tuple[RetrievalResult, ...]:
        return retrieve_chunks(query, chunks, limit=limit)


class LocalHashEmbeddingProvider:
    """Deterministic local embedding provider based on token hashing."""

    model = "local-hash-v1"
    api_version = 1
    kind = "embedding_provider"

    def __init__(self, dimensions: int = 64) -> None:
        if dimensions <= 0:
            raise ValueError("dimensions must be positive")
        self.dimensions = dimensions

    def embed_text(self, text: str) -> tuple[float, ...]:
        values = [0.0] * self.dimensions
        for token in _tokens(text):
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:4], "big") % self.dimensions
            values[index] += 1.0
        magnitude = math.sqrt(sum(value * value for value in values))
        if magnitude == 0.0:
            return tuple(values)
        return tuple(value / magnitude for value in values)


class LocalJsonVectorStore:
    """File-backed local vector store for deterministic offline retrieval."""

    filename = "vectors.json"
    api_version = 1
    kind = "vector_store"

    def write(
        self,
        index_dir: Path,
        chunks: tuple[DocumentationChunk, ...],
        provider: EmbeddingProvider,
    ) -> Path:
        path = index_dir / self.filename
        path.parent.mkdir(parents=True, exist_ok=True)
        cached: dict[tuple[str, str | None], tuple[float, ...]] = {}
        if path.is_file():
            try:
                existing = self.read(index_dir)
                if existing.embedding_model == provider.model and existing.dimensions == provider.dimensions:
                    cached = {(record.chunk_id, record.content_hash): record.embedding for record in existing.records}
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                cached = {}
        payload = {
            "schema_version": VECTOR_INDEX_SCHEMA_VERSION,
            "embedding_model": provider.model,
            "dimensions": provider.dimensions,
            "records": [
                {
                    "chunk_id": chunk.chunk_id,
                    "content_hash": chunk.content_hash,
                    "embedding": list(
                        cached.get((chunk.chunk_id, chunk.content_hash)) or provider.embed_text(chunk.text)
                    ),
                }
                for chunk in sorted(chunks, key=lambda item: item.chunk_id)
            ],
        }
        atomic_write_text(path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return path

    def read(self, index_dir: Path) -> VectorIndex:
        path = index_dir / self.filename
        payload = json.loads(path.read_text(encoding="utf-8"))
        return VectorIndex(
            schema_version=int(payload.get("schema_version", VECTOR_INDEX_SCHEMA_VERSION)),
            embedding_model=str(payload["embedding_model"]),
            dimensions=int(payload["dimensions"]),
            records=tuple(
                VectorRecord(
                    chunk_id=str(record["chunk_id"]),
                    content_hash=str(record["content_hash"]) if record.get("content_hash") is not None else None,
                    embedding=tuple(float(value) for value in record.get("embedding", ())),
                )
                for record in payload.get("records", ())
            ),
        )


class VectorRetriever:
    """Local vector retriever backed by a loaded vector index."""

    def __init__(self, index: VectorIndex, provider: EmbeddingProvider) -> None:
        if index.embedding_model != provider.model:
            raise ValueError(f"Vector index model mismatch: {index.embedding_model} != {provider.model}")
        if index.dimensions != provider.dimensions:
            raise ValueError(f"Vector index dimensions mismatch: {index.dimensions} != {provider.dimensions}")
        self.index = index
        self.provider = provider

    def retrieve(
        self,
        query: str,
        chunks: tuple[DocumentationChunk, ...],
        limit: int = 5,
    ) -> tuple[RetrievalResult, ...]:
        if limit <= 0:
            return ()
        query_vector = self.provider.embed_text(query)
        if not any(query_vector):
            return ()
        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        query_terms = tuple(dict.fromkeys(_tokens(query)))
        results: list[RetrievalResult] = []
        for record in self.index.records:
            chunk = chunks_by_id.get(record.chunk_id)
            if chunk is None:
                continue
            if (
                chunk.content_hash is not None
                and record.content_hash is not None
                and chunk.content_hash != record.content_hash
            ):
                continue
            score = _cosine(query_vector, record.embedding)
            if score <= 0.0:
                continue
            chunk_terms = set(_tokens(chunk.text))
            results.append(
                RetrievalResult(
                    chunk=chunk,
                    score=score,
                    matched_terms=tuple(term for term in query_terms if term in chunk_terms),
                )
            )
        return tuple(sorted(results, key=lambda result: (-result.score, result.chunk.chunk_id))[:limit])


def load_document(path: Path) -> LoadedDocument:
    """Load one supported local documentation file."""

    requested = path.expanduser()
    if requested.is_symlink():
        raise ValueError(f"Documentation input must not be a symbolic link: {requested}")
    source = requested.resolve(strict=False)
    if source.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError(f"Unsupported documentation file extension: {source.suffix}")
    if not source.is_file():
        raise ValueError(f"Documentation input is not a regular file: {source}")
    if source.stat().st_size > MAX_DOCUMENT_BYTES:
        raise ValueError(f"Documentation input exceeds {MAX_DOCUMENT_BYTES} byte safety limit: {source}")
    if source.suffix.lower() == ".pdf":
        return _load_pdf_document(source)
    text = source.read_text(encoding="utf-8")
    return LoadedDocument(source=source, text=_normalize_newlines(text))


def _load_pdf_document(source: Path) -> LoadedDocument:
    try:
        reader = PdfReader(source)
        if reader.is_encrypted and reader.decrypt("") == 0:
            raise ValueError(f"Encrypted PDF requires a password: {source}")
        if len(reader.pages) > MAX_PDF_PAGES:
            raise ValueError(f"PDF exceeds {MAX_PDF_PAGES} page safety limit: {source}")
        page_texts = tuple(_normalize_newlines(page.extract_text() or "").strip() for page in reader.pages)
    except ValueError:
        raise
    except Exception as error:
        raise ValueError(f"Could not extract PDF text from {source}: {error}") from error
    if not any(page_texts):
        raise ValueError(f"PDF has no extractable text; OCR is required: {source}")
    if sum(len(text) for text in page_texts) > MAX_EXTRACTED_TEXT_CHARACTERS:
        raise ValueError(f"PDF extracted text exceeds {MAX_EXTRACTED_TEXT_CHARACTERS} character safety limit: {source}")
    text_parts: list[str] = []
    page_ranges: list[tuple[int, int, int]] = []
    offset = 0
    for page_number, page_text in enumerate(page_texts, start=1):
        if text_parts:
            text_parts.append("\n\n")
            offset += 2
        start = offset
        text_parts.append(page_text)
        offset += len(page_text)
        page_ranges.append((page_number, start, offset))
    return LoadedDocument(source=source, text="".join(text_parts), page_ranges=tuple(page_ranges))


def load_documents(paths: tuple[Path, ...]) -> tuple[LoadedDocument, ...]:
    """Load supported documentation files in deterministic source order."""

    documents = [load_document(path) for path in paths if path.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS]
    return tuple(sorted(documents, key=lambda document: document.source.as_posix()))


def load_documents_with_adapters(
    paths: tuple[Path, ...],
    loaders: tuple[DocumentLoader, ...] = (),
) -> tuple[LoadedDocument, ...]:
    """Load documents through explicit adapters before the built-in parser."""

    documents: list[LoadedDocument] = []
    for path in paths:
        loader = next((item for item in loaders if item.supports(path)), None)
        if loader is not None:
            documents.append(loader.load(path))
        elif path.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS:
            documents.append(load_document(path))
    return tuple(sorted(documents, key=lambda document: document.source.as_posix()))


def discover_documentation_files(paths: tuple[Path, ...], loaders: tuple[DocumentLoader, ...] = ()) -> tuple[Path, ...]:
    """Discover supported documentation files from configured files or directories."""

    files: list[Path] = []
    for path in paths:
        source = path.expanduser().resolve(strict=False)
        if source.is_file() and (
            source.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS or any(loader.supports(source) for loader in loaders)
        ):
            files.append(source)
        elif source.is_dir():
            for candidate in source.rglob("*"):
                if any(part in SKIPPED_DOCUMENT_DIRECTORIES for part in candidate.relative_to(source).parts[:-1]):
                    continue
                if candidate.name.lower().endswith(".ocr.txt"):
                    continue
                if candidate.is_file() and (
                    candidate.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS
                    or any(loader.supports(candidate) for loader in loaders)
                ):
                    files.append(candidate.resolve(strict=False))
    return tuple(dict.fromkeys(sorted(files, key=lambda item: item.as_posix())))


def chunk_document(document: LoadedDocument, max_chars: int = 1200) -> tuple[DocumentationChunk, ...]:
    """Split a loaded document into stable paragraph-based chunks."""

    if max_chars <= 0:
        raise ValueError("max_chars must be positive")

    blocks = _text_blocks(document.text)
    chunks: list[DocumentationChunk] = []
    current_parts: list[str] = []
    current_start: int | None = None
    current_end = 0

    for start, end, text in blocks:
        proposed_text = text if not current_parts else "\n\n".join((*current_parts, text))
        if current_parts and len(proposed_text) > max_chars:
            chunks.append(_chunk(document, "\n\n".join(current_parts), current_start or 0, current_end))
            current_parts = [text]
            current_start = start
        else:
            current_parts.append(text)
            if current_start is None:
                current_start = start
        current_end = end

    if current_parts:
        chunks.append(_chunk(document, "\n\n".join(current_parts), current_start or 0, current_end))

    return tuple(chunks)


def chunk_documents(documents: tuple[LoadedDocument, ...], max_chars: int = 1200) -> tuple[DocumentationChunk, ...]:
    """Chunk loaded documents in deterministic source order."""

    chunks: list[DocumentationChunk] = []
    for document in sorted(documents, key=lambda item: item.source.as_posix()):
        chunks.extend(chunk_document(document, max_chars=max_chars))
    return tuple(chunks)


def write_document_index(config: CLIConfig, chunks: tuple[DocumentationChunk, ...]) -> Path:
    """Persist documentation chunks to the configured local retrieval index."""

    index_dir = config.retrieval_index_dir or config.work_dir / "rag-index"
    index_path = index_dir / "chunks.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": DOCUMENT_INDEX_SCHEMA_VERSION,
        "chunks": [_chunk_to_json(chunk) for chunk in sorted(chunks, key=lambda item: item.chunk_id)],
    }
    atomic_write_text(index_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    write_document_vector_index(index_dir, chunks)
    return index_path


def write_document_index_with_adapters(
    config: CLIConfig,
    chunks: tuple[DocumentationChunk, ...],
    provider: EmbeddingProvider,
    store: VectorStore,
) -> Path:
    """Persist chunks and vectors using explicitly selected production adapters."""

    index_dir = config.retrieval_index_dir or config.work_dir / "rag-index"
    index_path = index_dir / "chunks.json"
    index_path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": DOCUMENT_INDEX_SCHEMA_VERSION,
        "chunks": [_chunk_to_json(chunk) for chunk in sorted(chunks, key=lambda item: item.chunk_id)],
    }
    atomic_write_text(index_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    store.write(index_dir, chunks, provider)
    return index_path


def read_document_index(index_dir: Path) -> tuple[DocumentationChunk, ...]:
    """Read documentation chunks from a local retrieval index."""

    index_path = index_dir / "chunks.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return tuple(_chunk_from_json(item) for item in payload.get("chunks", ()))


def read_configured_document_index(config: CLIConfig) -> tuple[DocumentationChunk, ...]:
    """Read documentation chunks from the configured retrieval index."""

    return read_document_index(config.retrieval_index_dir or config.work_dir / "rag-index")


def write_document_vector_index(
    index_dir: Path,
    chunks: tuple[DocumentationChunk, ...],
    provider: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> Path:
    """Write a deterministic local vector index for documentation chunks."""

    return (store or LocalJsonVectorStore()).write(index_dir, chunks, provider or LocalHashEmbeddingProvider())


def read_document_vector_index(
    index_dir: Path,
    store: VectorStore | None = None,
) -> VectorIndex:
    """Read the configured local vector index."""

    return (store or LocalJsonVectorStore()).read(index_dir)


def retrieve_chunks_with_vectors(
    query: str,
    chunks: tuple[DocumentationChunk, ...],
    index_dir: Path,
    limit: int = 5,
    provider: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> tuple[RetrievalResult, ...]:
    """Retrieve documentation chunks through the local vector backend, falling back to lexical retrieval."""

    try:
        index = read_document_vector_index(index_dir, store)
        return VectorRetriever(index, provider or LocalHashEmbeddingProvider()).retrieve(query, chunks, limit=limit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError):
        return retrieve_chunks(query, chunks, limit=limit)


def retrieve_chunks(
    query: str,
    chunks: tuple[DocumentationChunk, ...],
    limit: int = 5,
) -> tuple[RetrievalResult, ...]:
    """Retrieve local documentation chunks with deterministic lexical scoring."""

    if limit <= 0:
        return ()

    query_terms = tuple(dict.fromkeys(_tokens(query)))
    if not query_terms:
        return ()

    results: list[RetrievalResult] = []
    for chunk in chunks:
        chunk_terms = _tokens(chunk.text)
        if not chunk_terms:
            continue

        frequencies: dict[str, int] = {}
        for term in chunk_terms:
            frequencies[term] = frequencies.get(term, 0) + 1
        matched_terms = tuple(term for term in query_terms if term in frequencies)
        if not matched_terms:
            continue

        frequency_score = sum(frequencies[term] for term in matched_terms)
        coverage_score = len(matched_terms) / len(query_terms)
        results.append(
            RetrievalResult(
                chunk=chunk,
                score=frequency_score + coverage_score,
                matched_terms=matched_terms,
            )
        )

    return tuple(
        sorted(
            results,
            key=lambda result: (-result.score, result.chunk.chunk_id),
        )[:limit]
    )


def _normalize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _tokens(text: str) -> tuple[str, ...]:
    return tuple(match.group(0).lower() for match in re.finditer(r"[A-Za-z0-9_]+", text))


def _cosine(left: tuple[float, ...], right: tuple[float, ...]) -> float:
    if len(left) != len(right):
        return 0.0
    return sum(left_value * right_value for left_value, right_value in zip(left, right, strict=True))


def _text_blocks(text: str) -> tuple[tuple[int, int, str], ...]:
    blocks: list[tuple[int, int, str]] = []
    offset = 0
    while offset < len(text):
        while offset < len(text) and text[offset].isspace():
            offset += 1
        if offset >= len(text):
            break

        delimiter = re.search(r"\n[ \t]*\n", text[offset:])
        if delimiter is None:
            end = len(text)
            next_offset = len(text)
        else:
            end = offset + delimiter.start()
            next_offset = offset + delimiter.end()

        while end > offset and text[end - 1].isspace():
            end -= 1
        if end > offset:
            blocks.append((offset, end, text[offset:end]))
        offset = next_offset
    return tuple(blocks)


def _chunk(document: LoadedDocument, text: str, start_offset: int, end_offset: int) -> DocumentationChunk:
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = f"{document.source.as_posix()}:{start_offset}:{end_offset}:{content_hash}"
    chunk_id = "doc:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    pages = tuple(
        page_number
        for page_number, page_start, page_end in document.page_ranges
        if start_offset < page_end and end_offset > page_start
    )
    source_locator = None
    if pages:
        source_locator = f"page:{pages[0]}" if len(pages) == 1 else f"pages:{pages[0]}-{pages[-1]}"
    return DocumentationChunk(
        chunk_id=chunk_id,
        source=document.source,
        text=text,
        start_offset=start_offset,
        end_offset=end_offset,
        content_hash=content_hash,
        source_locator=source_locator,
    )


def _chunk_to_json(chunk: DocumentationChunk) -> dict[str, object]:
    return {
        "chunk_id": chunk.chunk_id,
        "source": str(chunk.source),
        "text": chunk.text,
        "start_offset": chunk.start_offset,
        "end_offset": chunk.end_offset,
        "content_hash": chunk.content_hash,
        "embedding_model": chunk.embedding_model,
        "source_locator": chunk.source_locator,
    }


def _chunk_from_json(data: dict[str, Any]) -> DocumentationChunk:
    return DocumentationChunk(
        chunk_id=str(data["chunk_id"]),
        source=Path(str(data["source"])),
        text=str(data["text"]),
        start_offset=int(data["start_offset"]) if data.get("start_offset") is not None else None,
        end_offset=int(data["end_offset"]) if data.get("end_offset") is not None else None,
        content_hash=str(data["content_hash"]) if data.get("content_hash") is not None else None,
        embedding_model=str(data["embedding_model"]) if data.get("embedding_model") is not None else None,
        source_locator=str(data["source_locator"]) if data.get("source_locator") is not None else None,
    )


for _name, _value in tuple(globals().items()):
    if isinstance(_value, type) and getattr(_value, "__module__", None) == __name__:
        _value.__module__ = "dv_platform.analysis.docs"
