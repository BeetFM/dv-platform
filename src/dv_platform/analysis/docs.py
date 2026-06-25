"""Local documentation loading, chunking, and retrieval helpers."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import re

from dv_platform.core.models import DocumentationChunk
from dv_platform.core.models import CLIConfig


SUPPORTED_DOCUMENT_EXTENSIONS = {".md", ".markdown", ".rst", ".txt"}
SKIPPED_DOCUMENT_DIRECTORIES = {".git", ".hg", ".svn", ".dv-platform", "__pycache__"}


@dataclass(frozen=True)
class LoadedDocument:
    """A local documentation file loaded for indexing."""

    source: Path
    text: str


@dataclass(frozen=True)
class RetrievalResult:
    """A lexical retrieval hit from the local documentation index."""

    chunk: DocumentationChunk
    score: float
    matched_terms: tuple[str, ...]


def load_document(path: Path) -> LoadedDocument:
    """Load one supported local documentation file."""

    source = path.expanduser().resolve(strict=False)
    if source.suffix.lower() not in SUPPORTED_DOCUMENT_EXTENSIONS:
        raise ValueError(f"Unsupported documentation file extension: {source.suffix}")
    text = source.read_text(encoding="utf-8")
    return LoadedDocument(source=source, text=_normalize_newlines(text))


def load_documents(paths: tuple[Path, ...]) -> tuple[LoadedDocument, ...]:
    """Load supported documentation files in deterministic source order."""

    documents = [load_document(path) for path in paths if path.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS]
    return tuple(sorted(documents, key=lambda document: document.source.as_posix()))


def discover_documentation_files(paths: tuple[Path, ...]) -> tuple[Path, ...]:
    """Discover supported documentation files from configured files or directories."""

    files: list[Path] = []
    for path in paths:
        source = path.expanduser().resolve(strict=False)
        if source.is_file() and source.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS:
            files.append(source)
        elif source.is_dir():
            for candidate in source.rglob("*"):
                if any(part in SKIPPED_DOCUMENT_DIRECTORIES for part in candidate.relative_to(source).parts[:-1]):
                    continue
                if candidate.is_file() and candidate.suffix.lower() in SUPPORTED_DOCUMENT_EXTENSIONS:
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
            chunks.append(_chunk(document.source, "\n\n".join(current_parts), current_start or 0, current_end))
            current_parts = [text]
            current_start = start
        else:
            current_parts.append(text)
            if current_start is None:
                current_start = start
        current_end = end

    if current_parts:
        chunks.append(_chunk(document.source, "\n\n".join(current_parts), current_start or 0, current_end))

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
        "schema_version": 1,
        "chunks": [_chunk_to_json(chunk) for chunk in sorted(chunks, key=lambda item: item.chunk_id)],
    }
    index_path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return index_path


def read_document_index(index_dir: Path) -> tuple[DocumentationChunk, ...]:
    """Read documentation chunks from a local retrieval index."""

    index_path = index_dir / "chunks.json"
    payload = json.loads(index_path.read_text(encoding="utf-8"))
    return tuple(_chunk_from_json(item) for item in payload.get("chunks", ()))


def read_configured_document_index(config: CLIConfig) -> tuple[DocumentationChunk, ...]:
    """Read documentation chunks from the configured retrieval index."""

    return read_document_index(config.retrieval_index_dir or config.work_dir / "rag-index")


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


def _chunk(source: Path, text: str, start_offset: int, end_offset: int) -> DocumentationChunk:
    content_hash = hashlib.sha256(text.encode("utf-8")).hexdigest()
    identity = f"{source.as_posix()}:{start_offset}:{end_offset}:{content_hash}"
    chunk_id = "doc:" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:16]
    return DocumentationChunk(
        chunk_id=chunk_id,
        source=source,
        text=text,
        start_offset=start_offset,
        end_offset=end_offset,
        content_hash=content_hash,
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
    }


def _chunk_from_json(data: dict[str, object]) -> DocumentationChunk:
    return DocumentationChunk(
        chunk_id=str(data["chunk_id"]),
        source=Path(str(data["source"])),
        text=str(data["text"]),
        start_offset=int(data["start_offset"]) if data.get("start_offset") is not None else None,
        end_offset=int(data["end_offset"]) if data.get("end_offset") is not None else None,
        content_hash=str(data["content_hash"]) if data.get("content_hash") is not None else None,
        embedding_model=str(data["embedding_model"]) if data.get("embedding_model") is not None else None,
    )
