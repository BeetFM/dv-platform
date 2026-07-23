"""Generate deterministic sparse-free Stage 10 scale workloads."""

from __future__ import annotations

import argparse
from pathlib import Path

RTL_LINES = 2_000_000
XML_BYTES = 128 * 1024 * 1024
PDF_BYTES = 64 * 1024 * 1024


def generate(directory: Path) -> tuple[Path, Path, Path]:
    directory.mkdir(parents=True, exist_ok=True)
    rtl = directory / "scale.sv"
    xml = directory / "scale.xml"
    pdf = directory / "scale.pdf"
    _rtl(rtl)
    _xml(xml)
    _pdf(pdf)
    return rtl, xml, pdf


def _rtl(path: Path) -> None:
    with path.open("wb") as stream:
        line = b"wire scale_signal; // deterministic workload\n"
        for _index in range(RTL_LINES):
            stream.write(line)


def _xml(path: Path) -> None:
    element = b'<node kind="signal" width="32">0123456789abcdef</node>\n'
    with path.open("wb") as stream:
        stream.write(b"<design>\n")
        while stream.tell() + len(element) + len(b"</design>\n") < XML_BYTES:
            stream.write(element)
        remaining = XML_BYTES - stream.tell() - len(b"</design>\n")
        if remaining >= len(b"<pad></pad>\n"):
            payload = b"x" * (remaining - len(b"<pad></pad>\n"))
            stream.write(b"<pad>" + payload + b"</pad>\n")
        stream.write(b"</design>\n")


def _pdf(path: Path) -> None:
    # One uncompressed page content stream. PdfReader must parse and extract
    # the complete text, so the byte threshold is an actual parser workload.
    prefix = b"BT /F1 10 Tf 10 10 Td ("
    suffix = b") Tj ET\n"
    # A single large string keeps operator count bounded while requiring the
    # parser and extractor to consume the complete 64 MiB content payload.
    content = prefix + b"x" * (PDF_BYTES - len(prefix) - len(suffix)) + suffix
    objects = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
        b"<< /Length " + str(len(content)).encode() + b" >>\nstream\n" + content + b"endstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    with path.open("wb") as stream:
        stream.write(b"%PDF-1.7\n")
        offsets = [0]
        for index, body in enumerate(objects, start=1):
            offsets.append(stream.tell())
            stream.write(f"{index} 0 obj\n".encode() + body + b"\nendobj\n")
        xref = stream.tell()
        stream.write(f"xref\n0 {len(objects) + 1}\n".encode())
        stream.write(b"0000000000 65535 f \n")
        for offset in offsets[1:]:
            stream.write(f"{offset:010d} 00000 n \n".encode())
        stream.write(f"trailer\n<< /Size {len(objects) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n%%EOF\n".encode())


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    for path in generate(args.output):
        print(path)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
