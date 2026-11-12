"""Minimal DOCX table reader on ``zipfile`` + ``xml.etree`` (45a design D4).

No new dependency: a DOCX is a ZIP whose ``word/document.xml`` holds the body.
We only need, in document order, every top-level table with the paragraph that
precedes it (its caption, e.g. ``Tabla 9. Riesgos Altos``) and, per row, the
cell texts plus whether the row is a single cell spanning the whole grid
(``w:gridSpan``), which is how the PSPI marks its group rows.
"""

import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from xml.etree import ElementTree as ET

from app.modules.plans.importers.common import SourceFormatError

_W = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
_DOCUMENT = "word/document.xml"
#: Anti-bomb guard on the UNCOMPRESSED body size (real plans are < 1 MB).
MAX_DOCUMENT_XML_BYTES = 20 * 1024 * 1024


@dataclass(frozen=True)
class DocxRow:
    cells: list[str]
    #: A single cell spanning several grid columns (a group/section row).
    is_spanned: bool


@dataclass
class DocxTable:
    caption: str
    rows: list[DocxRow] = field(default_factory=list)

    @property
    def header(self) -> list[str]:
        return self.rows[0].cells if self.rows else []


def _text(element: ET.Element) -> str:
    paragraphs = [
        "".join(node.text or "" for node in paragraph.iter(f"{_W}t"))
        for paragraph in element.iter(f"{_W}p")
    ]
    return " ".join(" ".join(p.split()) for p in paragraphs if p.strip())


def _row(tr: ET.Element) -> DocxRow:
    cells = tr.findall(f"{_W}tc")
    spanned = False
    if len(cells) == 1:
        span = cells[0].find(f"{_W}tcPr/{_W}gridSpan")
        spanned = span is not None and int(span.get(f"{_W}val", "1")) > 1
    return DocxRow(cells=[_text(cell) for cell in cells], is_spanned=spanned)


def read_tables(path: Path) -> list[DocxTable]:
    """Return the top-level tables of ``path`` in document order."""

    try:
        with zipfile.ZipFile(path) as archive:
            info = archive.getinfo(_DOCUMENT)
            if info.file_size > MAX_DOCUMENT_XML_BYTES:
                raise SourceFormatError(
                    f"El documento {path.name} excede el tamaño máximo permitido."
                )
            raw = archive.read(_DOCUMENT)
    except (zipfile.BadZipFile, KeyError) as exc:
        raise SourceFormatError(
            f"El archivo {path.name} no es un documento Word (.docx) válido."
        ) from exc
    if b"<!DOCTYPE" in raw[:4096]:
        raise SourceFormatError(f"El documento {path.name} declara un DOCTYPE no permitido.")

    body = ET.fromstring(raw).find(f"{_W}body")
    if body is None:
        raise SourceFormatError(f"El documento {path.name} no tiene cuerpo.")
    tables: list[DocxTable] = []
    caption = ""
    for child in body:
        if child.tag == f"{_W}p":
            text = _text(child)
            if text:
                caption = text
        elif child.tag == f"{_W}tbl":
            tables.append(
                DocxTable(caption=caption, rows=[_row(tr) for tr in child.findall(f"{_W}tr")])
            )
    return tables
