import json
import sqlite3
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from dv_platform.analysis.docs import (
    LoadedDocument,
    LocalHashEmbeddingProvider,
    LocalJsonVectorStore,
    LocalSQLiteFTSStore,
    chunk_document,
    chunk_documents,
    load_document,
    load_documents,
    read_configured_document_index,
    read_document_index,
    read_document_vector_index,
    retrieve_chunks,
    retrieve_chunks_with_vectors,
    write_document_index,
)
from dv_platform.core.config import default_config
from tests.support.paths import FIXTURES_ROOT

FIXTURES = FIXTURES_ROOT / "docs"


class DocumentationLoadingTests(unittest.TestCase):
    def test_load_document_supports_markdown_text_and_rst(self) -> None:
        markdown = load_document(FIXTURES / "design.md")
        text = load_document(FIXTURES / "notes.txt")
        rst = load_document(FIXTURES / "reset.rst")

        self.assertEqual(markdown.source, (FIXTURES / "design.md").resolve(strict=False))
        self.assertIn("simple_counter", markdown.text)
        self.assertIn("Clock clk", text.text)
        self.assertIn("active low", rst.text)

    def test_load_document_normalizes_newlines(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "windows_newlines.txt"
            source.write_text("a\r\nb\rc\n", encoding="utf-8")

            document = load_document(source)

        self.assertEqual(document.text, "a\nb\nc\n")

    def test_load_document_rejects_unsupported_extensions(self) -> None:
        with TemporaryDirectory() as temp_dir:
            unsupported = Path(temp_dir) / "design.docx"
            unsupported.write_bytes(b"not a docx")
            with self.assertRaisesRegex(ValueError, "Unsupported documentation"):
                load_document(unsupported)

    def test_load_document_rejects_symlinks(self) -> None:
        with TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target.md"
            target.write_text("secret", encoding="utf-8")
            link = root / "link.md"
            link.symlink_to(target)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                load_document(link)

    def test_load_document_extracts_pdf_text_and_page_provenance(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "requirements.pdf"
            _write_text_pdf(source, "simple_counter shall clear count_o on reset")

            document = load_document(source)
            chunks = chunk_document(document)

            self.assertIn("simple_counter shall clear count_o", document.text)
            self.assertEqual(document.page_ranges, ((1, 0, len(document.text)),))
            self.assertEqual(chunks[0].source_locator, "page:1")

    def test_load_document_reports_pdf_without_extractable_text(self) -> None:
        with TemporaryDirectory() as temp_dir:
            source = Path(temp_dir) / "scan.pdf"
            source.write_bytes(b"%PDF-1.4\n%%EOF\n")

            with self.assertRaisesRegex(ValueError, "Could not extract PDF text|OCR is required"):
                load_document(source)

    def test_load_documents_filters_and_sorts_supported_files(self) -> None:
        documents = load_documents(
            (
                FIXTURES / "reset.rst",
                FIXTURES / "design.md",
                FIXTURES / "notes.txt",
            )
        )

        self.assertEqual(
            tuple(document.source.name for document in documents),
            ("design.md", "notes.txt", "reset.rst"),
        )


class DocumentationChunkingTests(unittest.TestCase):
    def test_chunk_document_records_offsets_hashes_and_stable_ids(self) -> None:
        document = LoadedDocument(
            source=(FIXTURES / "design.md").resolve(strict=False),
            text="First paragraph about simple_counter.\n\nSecond paragraph about enable_i.\n",
        )

        chunks = chunk_document(document, max_chars=48)
        repeated = chunk_document(document, max_chars=48)

        self.assertEqual(len(chunks), 2)
        self.assertEqual(tuple(chunk.chunk_id for chunk in chunks), tuple(chunk.chunk_id for chunk in repeated))
        self.assertEqual(chunks[0].start_offset, 0)
        self.assertEqual(chunks[0].end_offset, len("First paragraph about simple_counter."))
        self.assertEqual(chunks[0].text, "First paragraph about simple_counter.")
        self.assertEqual(len(chunks[0].content_hash or ""), 64)
        self.assertEqual(chunks[1].start_offset, 39)
        self.assertEqual(chunks[1].text, "Second paragraph about enable_i.")

    def test_chunk_documents_preserves_source_order(self) -> None:
        documents = (
            LoadedDocument(source=FIXTURES / "reset.rst", text="reset behavior\n"),
            LoadedDocument(source=FIXTURES / "design.md", text="counter behavior\n"),
        )

        chunks = chunk_documents(documents)

        self.assertEqual(tuple(chunk.source.name for chunk in chunks), ("design.md", "reset.rst"))

    def test_chunk_document_rejects_invalid_size(self) -> None:
        document = LoadedDocument(source=FIXTURES / "design.md", text="text")

        with self.assertRaisesRegex(ValueError, "max_chars"):
            chunk_document(document, max_chars=0)


class DocumentationIndexTests(unittest.TestCase):
    def test_sqlite_fts_is_default_and_deterministic(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            chunks = chunk_documents(
                (
                    LoadedDocument(source=repo / "b.md", text="clock reset behavior"),
                    LoadedDocument(source=repo / "a.md", text="clock reset behavior"),
                )
            )

            write_document_index(config, chunks)
            index_dir = config.retrieval_index_dir or config.work_dir / "rag-index"
            results = retrieve_chunks_with_vectors("clock reset", chunks, index_dir)

            self.assertTrue((index_dir / LocalSQLiteFTSStore.filename).is_file())
            self.assertEqual(
                tuple(result.chunk.chunk_id for result in results),
                tuple(sorted(chunk.chunk_id for chunk in chunks)),
            )

    def test_sqlite_fts_rejects_corruption_and_falls_back_offline(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            chunks = chunk_document(LoadedDocument(source=index_dir / "design.md", text="counter behavior"))
            (index_dir / LocalSQLiteFTSStore.filename).write_bytes(b"not sqlite")

            with self.assertRaises((ValueError, sqlite3.DatabaseError)):
                LocalSQLiteFTSStore().read(index_dir)
            results = retrieve_chunks_with_vectors("counter", chunks, index_dir)
            self.assertEqual(tuple(result.chunk for result in results), chunks)

    def test_sqlite_fts_rejects_symlink_index_directory(self) -> None:
        with TemporaryDirectory() as temp_dir:
            root = Path(temp_dir)
            target = root / "target"
            target.mkdir()
            link = root / "link"
            link.symlink_to(target, target_is_directory=True)
            with self.assertRaisesRegex(ValueError, "symbolic link"):
                LocalSQLiteFTSStore().write(link, (), LocalHashEmbeddingProvider())

    def test_sqlite_fts_rebuilds_atomically_from_legacy_json(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            chunks = chunk_document(LoadedDocument(source=index_dir / "design.md", text="counter behavior"))
            payload = {"schema_version": 2, "chunks": [_chunk_json_for_test(chunk) for chunk in chunks]}
            (index_dir / "chunks.json").write_text(json.dumps(payload), encoding="utf-8")
            LocalJsonVectorStore().write(index_dir, chunks, LocalHashEmbeddingProvider())

            index = read_document_vector_index(index_dir)

            self.assertEqual(tuple(record.chunk_id for record in index.records), (chunks[0].chunk_id,))
            self.assertTrue((index_dir / LocalSQLiteFTSStore.filename).is_file())
            self.assertFalse(tuple(index_dir.glob(".retrieval.sqlite3.*.tmp")))

    def test_sqlite_fts_concurrent_publication_is_consistent(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            first = chunk_document(LoadedDocument(source=index_dir / "first.md", text="first generation"))
            second = chunk_document(LoadedDocument(source=index_dir / "second.md", text="second generation"))
            store = LocalSQLiteFTSStore()
            with ThreadPoolExecutor(max_workers=2) as executor:
                futures = (
                    executor.submit(store.write, index_dir, first, LocalHashEmbeddingProvider()),
                    executor.submit(store.write, index_dir, second, LocalHashEmbeddingProvider()),
                )
                for future in futures:
                    future.result()

            chunks = store.read_chunks(index_dir)
            self.assertIn(chunks, (first, second))
            self.assertFalse((index_dir / ".publish.lock").exists())
            self.assertFalse(tuple(index_dir.glob(".retrieval.sqlite3.*.tmp")))

    def test_sqlite_fts_cancellation_leaves_previous_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            original = chunk_document(LoadedDocument(source=index_dir / "first.md", text="first generation"))
            LocalSQLiteFTSStore().write(index_dir, original, LocalHashEmbeddingProvider())
            cancelled = threading.Event()
            cancelled.set()

            with self.assertRaisesRegex(InterruptedError, "cancelled"):
                LocalSQLiteFTSStore(cancel_event=cancelled).write(
                    index_dir,
                    chunk_document(LoadedDocument(source=index_dir / "second.md", text="second generation")),
                    LocalHashEmbeddingProvider(),
                )

            self.assertEqual(LocalSQLiteFTSStore().read_chunks(index_dir), original)
            self.assertFalse(tuple(index_dir.glob(".retrieval.sqlite3.*.tmp")))

    def test_sqlite_fts_failed_replace_leaves_previous_generation(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            original = chunk_document(LoadedDocument(source=index_dir / "first.md", text="first generation"))
            replacement = chunk_document(LoadedDocument(source=index_dir / "second.md", text="second generation"))
            store = LocalSQLiteFTSStore()
            store.write(index_dir, original, LocalHashEmbeddingProvider())

            with (
                patch("dv_platform.documentation.indexing.os.replace", side_effect=PermissionError("denied")),
                self.assertRaisesRegex(PermissionError, "denied"),
            ):
                store.write(index_dir, replacement, LocalHashEmbeddingProvider())

            self.assertEqual(store.read_chunks(index_dir), original)
            self.assertFalse(tuple(index_dir.glob(".retrieval.sqlite3.*.tmp")))

    def test_sqlite_fts_rejects_replaced_source(self) -> None:
        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            source = index_dir / "design.md"
            source.write_text("original behavior", encoding="utf-8")
            chunks = chunk_document(load_document(source))
            LocalSQLiteFTSStore().write(index_dir, chunks, LocalHashEmbeddingProvider())
            source.write_text("replacement behavior", encoding="utf-8")

            with self.assertRaisesRegex(ValueError, "changed after indexing"):
                LocalSQLiteFTSStore().read_chunks(index_dir)

    def test_vector_store_reuses_unchanged_chunk_embeddings(self) -> None:
        class CountingProvider(LocalHashEmbeddingProvider):
            def __init__(self) -> None:
                super().__init__(dimensions=8)
                self.calls = 0

            def embed_text(self, text: str) -> tuple[float, ...]:
                self.calls += 1
                return super().embed_text(text)

        with TemporaryDirectory() as temp_dir:
            index_dir = Path(temp_dir)
            chunks = chunk_document(LoadedDocument(source=index_dir / "design.md", text="counter behavior"))
            provider = CountingProvider()
            store = LocalJsonVectorStore()

            store.write(index_dir, chunks, provider)
            store.write(index_dir, chunks, provider)

            self.assertEqual(provider.calls, 1)

    def test_document_index_round_trips_chunks_under_retrieval_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            document = LoadedDocument(source=repo / "docs" / "design.md", text="counter behavior\n")
            chunks = chunk_document(document)

            index_path = write_document_index(config, chunks)
            loaded = read_document_index(config.retrieval_index_dir or config.work_dir / "rag-index")
            vectors = read_document_vector_index(config.retrieval_index_dir or config.work_dir / "rag-index")

            self.assertEqual(index_path, repo / ".dv-platform" / "rag-index" / "chunks.json")
            self.assertEqual(loaded, chunks)
            self.assertEqual(vectors.embedding_model, LocalHashEmbeddingProvider.model)
            self.assertEqual(len(vectors.records), len(chunks))

    def test_read_configured_document_index_uses_retrieval_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            chunks = chunk_document(LoadedDocument(source=repo / "docs" / "design.md", text="counter behavior\n"))
            write_document_index(config, chunks)

            loaded = read_configured_document_index(config)

            self.assertEqual(loaded, chunks)

    def test_document_index_is_written_in_chunk_id_order(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            chunks = chunk_documents(
                (
                    LoadedDocument(source=repo / "b.md", text="second\n"),
                    LoadedDocument(source=repo / "a.md", text="first\n"),
                )
            )

            loaded = read_document_index(write_document_index(config, chunks).parent)

            self.assertEqual(
                tuple(chunk.chunk_id for chunk in loaded), tuple(sorted(chunk.chunk_id for chunk in chunks))
            )


class DocumentationRetrievalTests(unittest.TestCase):
    def test_retrieve_chunks_scores_and_ranks_lexical_matches(self) -> None:
        chunks = chunk_documents(
            (
                LoadedDocument(
                    source=FIXTURES / "design.md",
                    text="simple_counter increments count_o when enable_i is asserted. enable_i gates count_o.",
                ),
                LoadedDocument(
                    source=FIXTURES / "reset.rst",
                    text="rst_n clears count_o during reset.",
                ),
            )
        )

        results = retrieve_chunks("enable_i count_o", chunks)

        self.assertEqual(results[0].chunk.source.name, "design.md")
        self.assertEqual(results[0].matched_terms, ("enable_i", "count_o"))
        self.assertGreater(results[0].score, results[1].score)

    def test_retrieve_chunks_applies_limit_and_ignores_empty_queries(self) -> None:
        chunks = chunk_documents(
            (
                LoadedDocument(source=FIXTURES / "a.md", text="clock reset enable\n"),
                LoadedDocument(source=FIXTURES / "b.md", text="clock reset\n"),
            )
        )

        self.assertEqual(len(retrieve_chunks("clock", chunks, limit=1)), 1)
        self.assertEqual(retrieve_chunks("   ", chunks), ())
        self.assertEqual(retrieve_chunks("clock", chunks, limit=0), ())

    def test_retrieve_chunks_with_vectors_uses_local_vector_index(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            chunks = chunk_documents(
                (
                    LoadedDocument(
                        source=FIXTURES / "design.md", text="enable_i increments count_o counter behavior\n"
                    ),
                    LoadedDocument(source=FIXTURES / "reset.rst", text="rst_n clears count_o during reset\n"),
                )
            )
            index_dir = config.retrieval_index_dir or config.work_dir / "rag-index"
            write_document_index(config, chunks)

            results = retrieve_chunks_with_vectors("enable_i counter", chunks, index_dir)

            self.assertEqual(results[0].chunk.source.name, "design.md")
            self.assertGreater(results[0].score, 0.0)

    def test_retrieve_chunks_with_vectors_falls_back_to_lexical_when_vector_index_is_missing(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            chunks = chunk_documents(
                (
                    LoadedDocument(source=FIXTURES / "a.md", text="clock reset enable\n"),
                    LoadedDocument(source=FIXTURES / "b.md", text="clock reset\n"),
                )
            )

            results = retrieve_chunks_with_vectors("enable", chunks, repo / "missing-index")

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].chunk.source.name, "a.md")


def _write_text_pdf(path: Path, text: str) -> None:
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = f"BT /F1 12 Tf 72 720 Td ({escaped}) Tj ET".encode("ascii")
    objects = (
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    )
    data = bytearray(b"%PDF-1.4\n")
    offsets = [0]
    for index, body in enumerate(objects, start=1):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii"))
        data.extend(body)
        data.extend(b"\nendobj\n")
    xref = len(data)
    data.extend(f"xref\n0 {len(objects) + 1}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode("ascii"))
    path.write_bytes(bytes(data))


def _chunk_json_for_test(chunk) -> dict[str, object]:
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


if __name__ == "__main__":
    unittest.main()
