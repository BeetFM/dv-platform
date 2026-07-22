"""Qualified local adapters for document, OCR, reporting, and policy boundaries."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

from dv_platform.analysis.docs import LoadedDocument, load_document
from dv_platform.core.io import atomic_write_text


class LocalDocumentLoader:
    """Load the built-in text and extractable-PDF formats."""

    api_version = 1
    kind = "document_loader"
    extensions = frozenset({".md", ".markdown", ".rst", ".txt", ".pdf"})

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions

    def load(self, path: Path) -> LoadedDocument:
        return load_document(path)


class OCRSidecarDocumentLoader:
    """Import governed OCR text stored beside an image or scanned PDF."""

    api_version = 1
    kind = "document_loader"
    extensions = frozenset({".png", ".jpg", ".jpeg", ".tif", ".tiff", ".pdf"})

    def supports(self, path: Path) -> bool:
        return path.suffix.lower() in self.extensions and self._sidecar(path).is_file()

    def load(self, path: Path) -> LoadedDocument:
        source = path.expanduser().resolve(strict=True)
        sidecar = self._sidecar(source)
        if not sidecar.is_file():
            raise ValueError(f"OCR sidecar is missing: {sidecar}")
        text = sidecar.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
        if not text.strip():
            raise ValueError(f"OCR sidecar contains no text: {sidecar}")
        return LoadedDocument(source=source, text=text)

    @staticmethod
    def _sidecar(path: Path) -> Path:
        return path.with_suffix(path.suffix + ".ocr.txt")


class JsonManifestReportExporter:
    """Export a deterministic, content-addressed manifest of local reports."""

    api_version = 1
    kind = "report_exporter"

    def export(self, reports: tuple[Path, ...], output: Path) -> Path:
        resolved = tuple(sorted((path.resolve(strict=True) for path in reports), key=lambda path: path.as_posix()))
        payload = {
            "schema_version": 1,
            "reports": [
                {
                    "path": path.name,
                    "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
                    "size_bytes": path.stat().st_size,
                }
                for path in resolved
            ],
        }
        atomic_write_text(output, json.dumps(payload, indent=2, sort_keys=True) + "\n")
        return output


class RegexRedactionPolicy:
    """Apply configured regular-expression redaction without exposing matches."""

    api_version = 1
    kind = "redaction_policy"

    def redact(self, text: str, patterns: tuple[str, ...]) -> str:
        result = text
        for pattern in patterns:
            result = re.sub(pattern, "[REDACTED]", result)
        return result
