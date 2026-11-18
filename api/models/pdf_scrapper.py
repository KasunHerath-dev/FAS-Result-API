"""
PDF Scrapper Module.
Extracts raw text and table layouts from scanned and digital academic PDFs
using low-RAM streaming generators and Tesseract OCR.
"""

import os
import gc
import re
import tempfile
from pathlib import Path
from typing import Generator, Optional, Tuple
import pypdf
import pytesseract
from pdf2image import convert_from_path
from PIL import Image, ImageEnhance


class PDFScrapperException(Exception):
    """Base exception for PDF Scrapper errors."""
    pass


class PDFScrapper:
    """
    High-performance, memory-conscious PDF extractor for FAS examination result sheets.
    Capable of handling scanned landscape photocopies (Canon iR2925), auto-detecting
    repeat examination sections, and streaming raw text to disk buffers.
    """

    def __init__(
        self,
        pdf_path: str | Path,
        temp_dir: Optional[str | Path] = None,
        ocr_dpi: int = 300,
        tesseract_cmd: Optional[str] = None,
        min_native_char_count: int = 50
    ):
        self.pdf_path = Path(pdf_path)
        if not self.pdf_path.exists():
            raise FileNotFoundError(f"PDF file not found at: {self.pdf_path}")

        self.temp_dir = Path(temp_dir) if temp_dir else None
        if self.temp_dir:
            self.temp_dir.mkdir(parents=True, exist_ok=True)

        self.ocr_dpi = ocr_dpi
        self.min_native_char_count = min_native_char_count
        self._temp_files: list[Path] = []

        if tesseract_cmd:
            pytesseract.pytesseract.tesseract_cmd = tesseract_cmd

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.cleanup()

    def cleanup(self) -> None:
        """Removes all temporary files generated during this scraper session."""
        for temp_file in self._temp_files:
            try:
                if temp_file.exists():
                    temp_file.unlink()
            except Exception:
                pass
        self._temp_files.clear()

    def preprocess_image(self, image: Image.Image) -> Image.Image:
        """
        Preprocesses mark sheet scan images to optimize OCR precision:
        - Detects portrait orientation and rotates 270 degrees to landscape if needed.
        - Converts to Grayscale.
        - Gently enhances contrast for clear character borders.
        """
        # Ensure landscape orientation for wide mark sheet tables
        if image.height > image.width:
            image = image.rotate(270, expand=True)

        gray = image.convert("L")
        enhancer = ImageEnhance.Contrast(gray)
        enhanced = enhancer.enhance(1.2)
        return enhanced

    def extract_page_ocr(self, page_image: Image.Image, psm: int = 3) -> str:
        """
        Extracts tabular text from a single page image using PyTesseract.
        Uses PSM 3 (fully automatic page segmentation) for robust layout reading.
        """
        try:
            processed_img = self.preprocess_image(page_image)
            custom_config = f"--oem 3 --psm {psm}"
            return pytesseract.image_to_string(processed_img, config=custom_config, lang="eng")
        except Exception as e:
            raise PDFScrapperException(f"Tesseract OCR extraction failed: {e}") from e

    def get_page_count(self) -> int:
        """Returns the total number of pages in the PDF document."""
        try:
            reader = pypdf.PdfReader(str(self.pdf_path))
            return len(reader.pages)
        except Exception as e:
            raise PDFScrapperException(f"Failed to read PDF page count: {e}") from e

    def stream_pages(self) -> Generator[Tuple[int, str, bool, str], None, None]:
        """
        Memory-efficient generator that yields:
          (page_number, extraction_mode, is_repeat_section, page_text)

        Renders one page image at a time, immediately reclaiming RAM memory to avoid
        OOM crashes on large, high-resolution scanned batches.
        """
        try:
            reader = pypdf.PdfReader(str(self.pdf_path))
            total_pages = len(reader.pages)

            for page_idx in range(total_pages):
                page_num = page_idx + 1
                page = reader.pages[page_idx]
                native_text = page.extract_text() or ""

                if len(native_text.strip()) >= self.min_native_char_count:
                    text = native_text
                    mode = "native"
                else:
                    images = convert_from_path(
                        str(self.pdf_path),
                        dpi=self.ocr_dpi,
                        first_page=page_num,
                        last_page=page_num
                    )
                    if not images:
                        raise PDFScrapperException(f"Rendering failed for page {page_num}")

                    page_img = images[0]
                    try:
                        text = self.extract_page_ocr(page_img)
                        mode = "ocr"
                    finally:
                        del page_img
                        del images
                        gc.collect()

                # Detect if the page belongs to the Repeat Examination session
                is_repeat = bool(re.search(r"(-Repeat|Repeat,|Repeat\s+Examination)", text, re.IGNORECASE))

                yield (page_num, mode, is_repeat, text)

        except Exception as e:
            if not isinstance(e, PDFScrapperException):
                raise PDFScrapperException(f"Error processing PDF '{self.pdf_path}': {e}") from e
            raise

    def extract_to_temp_file(self) -> Path:
        """
        Extracts the full PDF text into a temporary UTF-8 file with page and section boundaries.
        Returns the temporary file path, keeping process heap memory minimal.
        """
        temp_file = tempfile.NamedTemporaryFile(
            mode="w+",
            encoding="utf-8",
            delete=False,
            dir=self.temp_dir,
            suffix=".txt"
        )
        temp_path = Path(temp_file.name)
        self._temp_files.append(temp_path)

        try:
            for page_num, mode, is_repeat, text in self.stream_pages():
                section_tag = "REPEAT SECTION" if is_repeat else "REGULAR SECTION"
                temp_file.write(f"\n--- [PAGE {page_num} START | MODE: {mode} | {section_tag}] ---\n")
                temp_file.write(text)
                temp_file.write(f"\n--- [PAGE {page_num} END] ---\n")
            temp_file.flush()
            return temp_path
        finally:
            temp_file.close()
