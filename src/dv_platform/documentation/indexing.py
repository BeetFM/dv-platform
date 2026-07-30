"""Local documentation loading, chunking, and retrieval helpers."""

from __future__ import annotations

import hashlib
import json
import math
import os
import re
import sqlite3
import tempfile
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from pypdf import PdfReader

from dv_platform.core.io import atomic_write_text
from dv_platform.core.models import CLIConfig, DocumentationChunk
from dv_platform.infrastructure.locking import DirectoryLock

SUPPORTED_DOCUMENT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt", ".pdf"}
SKIPPED_DOCUMENT_DIRECTORIES = {".git", ".hg", ".svn", ".dv-platform", "__pycache__"}
DOCUMENT_INDEX_SCHEMA_VERSION = 2
VECTOR_INDEX_SCHEMA_VERSION = 1
SQLITE_INDEX_SCHEMA_VERSION = 2
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


class LocalSQLiteFTSStore:
    """Atomic SQLite FTS5 index used by the default offline retriever."""

    filename = "retrieval.sqlite3"
    api_version = 1
    kind = "vector_store"

    def __init__(
        self,
        index_dir: Path | None = None,
        *,
        cancel_event: threading.Event | None = None,
    ) -> None:
        self._index_dir = index_dir
        self._cancel_event = cancel_event

    def write(
        self,
        index_dir: Path,
        chunks: tuple[DocumentationChunk, ...],
        provider: EmbeddingProvider,
    ) -> Path:
        index_dir = _safe_index_directory(index_dir)
        index_dir.mkdir(parents=True, exist_ok=True)
        with DirectoryLock(index_dir / ".publish.lock"):
            return self._write_locked(index_dir, chunks, provider)

    def _write_locked(
        self,
        index_dir: Path,
        chunks: tuple[DocumentationChunk, ...],
        provider: EmbeddingProvider,
    ) -> Path:
        _raise_index_cancelled(self._cancel_event)
        descriptor, temporary_name = tempfile.mkstemp(prefix=f".{self.filename}.", suffix=".tmp", dir=index_dir)
        os.close(descriptor)
        temporary = Path(temporary_name)
        path = index_dir / self.filename
        try:
            with sqlite3.connect(temporary) as database:
                database.execute(f"PRAGMA user_version = {SQLITE_INDEX_SCHEMA_VERSION}")
                database.executescript(
                    """
                    CREATE TABLE metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL) WITHOUT ROWID;
                    CREATE TABLE chunks(
                        chunk_id TEXT PRIMARY KEY,
                        source TEXT NOT NULL,
                        source_locator TEXT,
                        start_offset INTEGER,
                        end_offset INTEGER,
                        content_hash TEXT NOT NULL,
                        source_sha256 TEXT,
                        text TEXT NOT NULL,
                        embedding TEXT NOT NULL
                    ) WITHOUT ROWID;
                    CREATE VIRTUAL TABLE chunks_fts USING fts5(
                        chunk_id UNINDEXED,
                        text,
                        tokenize='unicode61'
                    );
                    """
                )
                database.executemany(
                    "INSERT INTO metadata(key, value) VALUES (?, ?)",
                    (
                        ("embedding_model", provider.model),
                        ("dimensions", str(provider.dimensions)),
                        ("ranking", "fts5-bm25-v1;tie=chunk_id"),
                        ("row_count", str(len(chunks))),
                        ("chunk_manifest_sha256", _chunk_manifest_digest(chunks)),
                    ),
                )
                for chunk in sorted(chunks, key=lambda item: item.chunk_id):
                    _raise_index_cancelled(self._cancel_event)
                    content_hash = chunk.content_hash or hashlib.sha256(chunk.text.encode("utf-8")).hexdigest()
                    source_sha256 = _source_digest(chunk.source)
                    embedding = provider.embed_text(chunk.text)
                    database.execute(
                        """
                        INSERT INTO chunks(
                            chunk_id, source, source_locator, start_offset, end_offset,
                            content_hash, source_sha256, text, embedding
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            chunk.chunk_id,
                            str(chunk.source),
                            chunk.source_locator,
                            chunk.start_offset,
                            chunk.end_offset,
                            content_hash,
                            source_sha256,
                            chunk.text,
                            json.dumps(embedding, separators=(",", ":")),
                        ),
                    )
                    database.execute(
                        "INSERT INTO chunks_fts(chunk_id, text) VALUES (?, ?)",
                        (chunk.chunk_id, chunk.text),
                    )
                database.commit()
                if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
                    raise ValueError("SQLite retrieval index failed integrity check")
            os.replace(temporary, path)
            path.chmod(0o600)
        except BaseException:
            temporary.unlink(missing_ok=True)
            raise
        return path

    def read_chunks(self, index_dir: Path) -> tuple[DocumentationChunk, ...]:
        """Read the canonical chunk generation from SQLite."""

        path = _safe_index_path(index_dir, self.filename)
        with _open_sqlite_readonly(path) as database:
            self._validate(database)
            rows = database.execute(
                """
                SELECT chunk_id, source, text, start_offset, end_offset,
                       content_hash, source_locator, source_sha256
                FROM chunks ORDER BY chunk_id
                """
            )
            raw_rows = tuple(rows)
            stale_sources = tuple(
                str(source)
                for _chunk_id, source, _text, _start, _end, _content, _locator, source_sha256 in raw_rows
                if not _source_is_current(Path(str(source)), source_sha256)
            )
            if stale_sources:
                raise ValueError(f"documentation sources changed after indexing: {', '.join(stale_sources)}")
            chunks = tuple(
                DocumentationChunk(
                    chunk_id=str(chunk_id),
                    source=Path(str(source)),
                    text=str(text),
                    start_offset=int(start_offset) if start_offset is not None else None,
                    end_offset=int(end_offset) if end_offset is not None else None,
                    content_hash=str(content_hash),
                    source_locator=str(source_locator) if source_locator is not None else None,
                )
                for chunk_id, source, text, start_offset, end_offset, content_hash, source_locator, _source_sha256 in raw_rows
            )
        return chunks

    def read(self, index_dir: Path) -> VectorIndex:
        path = _safe_index_path(index_dir, self.filename)
        with _open_sqlite_readonly(path) as database:
            metadata = self._validate(database)
            records = tuple(
                VectorRecord(
                    chunk_id=str(chunk_id),
                    content_hash=str(content_hash),
                    embedding=tuple(float(value) for value in json.loads(str(embedding))),
                )
                for chunk_id, content_hash, embedding in database.execute(
                    "SELECT chunk_id, content_hash, embedding FROM chunks ORDER BY chunk_id"
                )
            )
        return VectorIndex(
            schema_version=SQLITE_INDEX_SCHEMA_VERSION,
            embedding_model=metadata["embedding_model"],
            dimensions=int(metadata["dimensions"]),
            records=records,
        )

    def retrieve(
        self,
        query: str,
        chunks: tuple[DocumentationChunk, ...],
        limit: int = 5,
    ) -> tuple[RetrievalResult, ...]:
        terms = tuple(dict.fromkeys(_tokens(query)))
        if limit <= 0 or not terms:
            return ()
        if self._index_dir is None:
            raise ValueError("SQLite retrieval store is not bound to an index directory")
        path = _safe_index_path(self._index_dir, self.filename)
        chunks_by_id = {chunk.chunk_id: chunk for chunk in chunks}
        expression = " OR ".join(f'"{term}"' for term in terms)
        results: list[RetrievalResult] = []
        with _open_sqlite_readonly(path) as database:
            self._validate(database)
            rows = database.execute(
                """
                SELECT f.chunk_id, bm25(chunks_fts) AS rank, c.content_hash
                FROM chunks_fts AS f JOIN chunks AS c ON c.chunk_id = f.chunk_id
                WHERE chunks_fts MATCH ?
                ORDER BY rank ASC, f.chunk_id ASC
                LIMIT ?
                """,
                (expression, limit),
            )
            for chunk_id, rank, content_hash in rows:
                chunk = chunks_by_id.get(str(chunk_id))
                if chunk is None or (chunk.content_hash is not None and chunk.content_hash != content_hash):
                    continue
                chunk_terms = set(_tokens(chunk.text))
                results.append(
                    RetrievalResult(
                        chunk=chunk,
                        score=-float(rank),
                        matched_terms=tuple(term for term in terms if term in chunk_terms),
                    )
                )
        return tuple(results)

    def bind(self, index_dir: Path) -> LocalSQLiteFTSStore:
        """Bind a store instance to an index directory for retrieval."""

        return LocalSQLiteFTSStore(index_dir, cancel_event=self._cancel_event)

    @staticmethod
    def _validate(database: sqlite3.Connection) -> dict[str, str]:
        if database.execute("PRAGMA user_version").fetchone() != (SQLITE_INDEX_SCHEMA_VERSION,):
            raise ValueError("unsupported SQLite retrieval index schema")
        if database.execute("PRAGMA integrity_check").fetchone() != ("ok",):
            raise ValueError("corrupt SQLite retrieval index")
        required = {"metadata", "chunks", "chunks_fts"}
        tables = {
            str(row[0]) for row in database.execute("SELECT name FROM sqlite_master WHERE type IN ('table', 'view')")
        }
        if not required <= tables:
            raise ValueError("SQLite retrieval index is missing required tables")
        metadata = {str(key): str(value) for key, value in database.execute("SELECT key, value FROM metadata")}
        if not {"embedding_model", "dimensions", "ranking", "row_count", "chunk_manifest_sha256"} <= metadata.keys():
            raise ValueError("SQLite retrieval index metadata is incomplete")
        row_count = int(database.execute("SELECT count(*) FROM chunks").fetchone()[0])
        fts_count = int(database.execute("SELECT count(*) FROM chunks_fts").fetchone()[0])
        if row_count != int(metadata["row_count"]) or fts_count != row_count:
            raise ValueError("SQLite retrieval index row count mismatch")
        stale = tuple(
            str(source)
            for source, source_sha256 in database.execute("SELECT DISTINCT source, source_sha256 FROM chunks")
            if not _source_is_current(Path(str(source)), source_sha256)
        )
        if stale:
            raise ValueError(f"documentation sources changed after indexing: {', '.join(stale)}")
        return metadata


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
    write_document_vector_index(index_dir, chunks)
    atomic_write_text(index_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
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
    store.write(index_dir, chunks, provider)
    atomic_write_text(index_path, json.dumps(payload, indent=2, sort_keys=True) + "\n")
    return index_path


def read_document_index(index_dir: Path) -> tuple[DocumentationChunk, ...]:
    """Read documentation chunks from a local retrieval index."""

    sqlite_path = index_dir / LocalSQLiteFTSStore.filename
    if sqlite_path.is_file() and not sqlite_path.is_symlink():
        return LocalSQLiteFTSStore().read_chunks(index_dir)
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

    return (store or LocalSQLiteFTSStore()).write(index_dir, chunks, provider or LocalHashEmbeddingProvider())


def read_document_vector_index(
    index_dir: Path,
    store: VectorStore | None = None,
) -> VectorIndex:
    """Read the configured local vector index."""

    selected = store or LocalSQLiteFTSStore()
    try:
        return selected.read(index_dir)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.DatabaseError):
        if store is not None:
            raise
        legacy = LocalJsonVectorStore().read(index_dir)
        chunks = _read_legacy_chunks(index_dir)
        provider = LocalHashEmbeddingProvider(legacy.dimensions)
        LocalSQLiteFTSStore().write(index_dir, chunks, provider)
        return LocalSQLiteFTSStore().read(index_dir)


def retrieve_chunks_with_vectors(
    query: str,
    chunks: tuple[DocumentationChunk, ...],
    index_dir: Path,
    limit: int = 5,
    provider: EmbeddingProvider | None = None,
    store: VectorStore | None = None,
) -> tuple[RetrievalResult, ...]:
    """Retrieve documentation chunks through the local vector backend, falling back to lexical retrieval."""

    selected = store or LocalSQLiteFTSStore()
    try:
        if isinstance(selected, LocalSQLiteFTSStore):
            return selected.bind(index_dir).retrieve(query, chunks, limit=limit)
        index = read_document_vector_index(index_dir, selected)
        return VectorRetriever(index, provider or LocalHashEmbeddingProvider()).retrieve(query, chunks, limit=limit)
    except (OSError, ValueError, KeyError, json.JSONDecodeError, sqlite3.DatabaseError):
        if store is None:
            try:
                index = LocalJsonVectorStore().read(index_dir)
                return VectorRetriever(index, provider or LocalHashEmbeddingProvider()).retrieve(
                    query, chunks, limit=limit
                )
            except (OSError, ValueError, KeyError, json.JSONDecodeError):
                pass
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


def _safe_index_directory(index_dir: Path) -> Path:
    requested = index_dir.expanduser()
    if requested.is_symlink():
        raise ValueError(f"Retrieval index directory must not be a symbolic link: {requested}")
    return requested.resolve(strict=False)


def _safe_index_path(index_dir: Path, filename: str) -> Path:
    directory = _safe_index_directory(index_dir)
    path = directory / filename
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"Retrieval index must be a regular file: {path}")
    if path.parent != directory:
        raise ValueError("Retrieval index path escapes configured directory")
    return path


def _open_sqlite_readonly(path: Path) -> sqlite3.Connection:
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def _read_legacy_chunks(index_dir: Path) -> tuple[DocumentationChunk, ...]:
    path = _safe_index_directory(index_dir) / "chunks.json"
    if path.is_symlink() or not path.is_file():
        raise ValueError("legacy vector index has no regular chunks.json")
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict) or payload.get("schema_version") != DOCUMENT_INDEX_SCHEMA_VERSION:
        raise ValueError("legacy document index schema is unsupported")
    chunks = payload.get("chunks")
    if not isinstance(chunks, list):
        raise ValueError("legacy document index chunks must be an array")
    return tuple(_chunk_from_json(item) for item in chunks)


def _chunk_manifest_digest(chunks: tuple[DocumentationChunk, ...]) -> str:
    rows = [
        (
            chunk.chunk_id,
            str(chunk.source),
            chunk.content_hash or hashlib.sha256(chunk.text.encode("utf-8")).hexdigest(),
            _source_digest(chunk.source),
        )
        for chunk in sorted(chunks, key=lambda item: item.chunk_id)
    ]
    return hashlib.sha256(json.dumps(rows, separators=(",", ":")).encode("utf-8")).hexdigest()


def _source_digest(source: Path) -> str | None:
    if source.is_symlink() or not source.is_file():
        return None
    return hashlib.sha256(source.read_bytes()).hexdigest()


def _source_is_current(source: Path, expected: object) -> bool:
    if expected is None or not source.exists():
        return True
    return isinstance(expected, str) and _source_digest(source) == expected


def _raise_index_cancelled(cancel_event: threading.Event | None) -> None:
    if cancel_event is not None and cancel_event.is_set():
        raise InterruptedError("documentation index publication cancelled")


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
