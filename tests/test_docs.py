from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

from dv_platform.analysis.docs import (
    LoadedDocument,
    chunk_document,
    chunk_documents,
    load_document,
    load_documents,
    read_configured_document_index,
    read_document_index,
    retrieve_chunks,
    write_document_index,
)
from dv_platform.core.config import default_config


FIXTURES = Path(__file__).parent / "fixtures" / "docs"


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
        with self.assertRaisesRegex(ValueError, "Unsupported documentation"):
            load_document(FIXTURES / "ignore.pdf")

    def test_load_documents_filters_and_sorts_supported_files(self) -> None:
        documents = load_documents(
            (
                FIXTURES / "reset.rst",
                FIXTURES / "ignore.pdf",
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
    def test_document_index_round_trips_chunks_under_retrieval_dir(self) -> None:
        with TemporaryDirectory() as temp_dir:
            repo = Path(temp_dir)
            config = default_config(repo)
            document = LoadedDocument(source=repo / "docs" / "design.md", text="counter behavior\n")
            chunks = chunk_document(document)

            index_path = write_document_index(config, chunks)
            loaded = read_document_index(config.retrieval_index_dir or config.work_dir / "rag-index")

            self.assertEqual(index_path, repo / ".dv-platform" / "rag-index" / "chunks.json")
            self.assertEqual(loaded, chunks)

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

            self.assertEqual(tuple(chunk.chunk_id for chunk in loaded), tuple(sorted(chunk.chunk_id for chunk in chunks)))


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


if __name__ == "__main__":
    unittest.main()
