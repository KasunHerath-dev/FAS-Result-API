"""Apply human-verified cell readings to the exact PDF they were checked against."""

import hashlib
import logging
from pathlib import Path

from pydantic import BaseModel, Field

from .table_ocr import GRADES, INDEX_PATTERN, GridPage

logger = logging.getLogger(__name__)


class ReviewedCell(BaseModel):
    page: int = Field(ge=1)
    row: int = Field(ge=1)
    column: str
    value: str


class OCRReview(BaseModel):
    source_sha256: str
    page_rows: list[int]
    cells: list[ReviewedCell]

    @classmethod
    def for_pdf(cls, review_file: Path, pdf: Path) -> "OCRReview":
        review = cls.model_validate_json(review_file.read_text(encoding="utf-8"))
        if review.source_sha256 != cls._pdf_digest(pdf):
            raise ValueError("OCR review belongs to a different PDF.")
        return review

    @classmethod
    def find_for_pdf(cls, pdf: Path, review_dir: Path) -> "OCRReview | None":
        name = f"{pdf.stem}-review.json"
        candidates = dict.fromkeys((pdf.with_name(name), review_dir / name))
        digest = None
        for candidate in candidates:
            if not candidate.is_file():
                continue
            try:
                review = cls.model_validate_json(candidate.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                logger.warning("Could not read the local OCR review at %s", candidate)
                continue
            digest = digest or cls._pdf_digest(pdf)
            if review.source_sha256 == digest:
                return review
            logger.warning("Ignored OCR review at %s because its PDF fingerprint differs", candidate)
        return None

    @staticmethod
    def _pdf_digest(pdf: Path) -> str:
        with pdf.open("rb") as source:
            return hashlib.file_digest(source, "sha256").hexdigest()

    def apply(self, pages: list[tuple[int, str, bool, str]]) -> list[tuple[int, str, bool, str]]:
        if len(pages) != len(self.page_rows) or any(mode != "ocr-grid" for _, mode, _, _ in pages):
            raise ValueError("OCR review requires the same ruled pages as the reviewed PDF.")
        grids = {number: GridPage.model_validate_json(text) for number, _, _, text in pages}
        if [len(grid.rows) for grid in grids.values()] != self.page_rows:
            raise ValueError("OCR row counts changed since the PDF was reviewed.")

        seen = set()
        for cell in self.cells:
            key = (cell.page, cell.row, cell.column)
            grid = grids.get(cell.page)
            if key in seen or grid is None or cell.row > len(grid.rows):
                raise ValueError(f"Invalid or duplicate reviewed cell {key}.")
            seen.add(key)
            row = grid.rows[cell.row - 1]
            if cell.column == "serial" and cell.value.isdecimal():
                row.serial = cell.value
            elif cell.column == "index" and INDEX_PATTERN.fullmatch(cell.value):
                row.index = cell.value
                grid.warnings = [warning for warning in grid.warnings if not warning.startswith(f"Row {cell.row} (serial ")]
            elif cell.column == "combination" and cell.value in {"1", "2", "3"}:
                row.combination = cell.value
            else:
                courses = [code for code, _ in grid.courses]
                if cell.column not in courses or cell.value not in GRADES | {""}:
                    raise ValueError(f"Invalid reviewed value for cell {key}.")
                row.grades[courses.index(cell.column)] = cell.value
                prefix = f"Serial {row.serial or '?'}, {cell.column}:"
                grid.warnings = [warning for warning in grid.warnings if not warning.startswith(prefix)]
        return [(page, mode, repeat, grids[page].model_dump_json()) for page, mode, repeat, _ in pages]
