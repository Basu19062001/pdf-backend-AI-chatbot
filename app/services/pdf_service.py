from __future__ import annotations

from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from typing import Any
import asyncio
import importlib
import re

from fastapi import HTTPException, status

from app.core.config import settings
from app.logger import get_logger

logger = get_logger(__name__)


@dataclass(slots=True)
class PageAnalysis:
    page_number: int
    word_count: int
    image_count: int
    image_area_ratio: float
    table_count: int
    classification: str
    extractors: tuple[str, ...]


@dataclass(slots=True)
class ExtractedPDFPage:
    page_number: int
    text: str
    analysis: PageAnalysis


@dataclass(slots=True)
class PDFExtractionResult:
    pages: list[ExtractedPDFPage]

    @property
    def page_texts(self) -> list[str]:
        return [page.text for page in self.pages]

    @property
    def summary(self) -> str:
        classifications: dict[str, int] = {}
        extractors: dict[str, int] = {}
        for page in self.pages:
            classifications[page.analysis.classification] = classifications.get(page.analysis.classification, 0) + 1
            for extractor in page.analysis.extractors:
                extractors[extractor] = extractors.get(extractor, 0) + 1

        classification_text = ", ".join(
            f"{name}={count}" for name, count in sorted(classifications.items())
        ) or "none"
        extractor_text = ", ".join(f"{name}={count}" for name, count in sorted(extractors.items())) or "none"
        return f"classifications[{classification_text}] extractors[{extractor_text}]"


class PDFService:
    """Analyze PDF pages and choose extraction strategies per page."""

    def validate_pdf_path(self, file_path: str) -> bool:
        path = Path(file_path)
        return path.exists() and path.suffix.lower() == ".pdf"

    async def extract_document(self, file_path: Path) -> PDFExtractionResult:
        if not self.validate_pdf_path(str(file_path)):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Invalid PDF file path provided for extraction",
            )

        logger.info("Starting PDF extraction workflow for '%s'.", file_path)
        return await asyncio.to_thread(self._extract_document_sync, file_path)

    def _extract_document_sync(self, file_path: Path) -> PDFExtractionResult:
        fitz = self._load_module("fitz", feature_name="PyMuPDF")
        document = fitz.open(file_path)
        try:
            plumber_pdf = self._open_pdfplumber(file_path)
            try:
                logger.info(
                    "Opened PDF '%s'. page_count=%s pdfplumber_enabled=%s",
                    file_path,
                    document.page_count,
                    plumber_pdf is not None,
                )
                extracted_pages: list[ExtractedPDFPage] = []
                for page_index in range(document.page_count):
                    page_number = page_index + 1
                    logger.info("Analyzing PDF page %s/%s for '%s'.", page_number, document.page_count, file_path)
                    fitz_page = document.load_page(page_index)
                    plumber_page = plumber_pdf.pages[page_index] if plumber_pdf is not None else None
                    analysis = self._analyze_page(
                        fitz_page=fitz_page,
                        plumber_page=plumber_page,
                        page_number=page_number,
                    )
                    logger.info(
                        "Page %s analysis completed for '%s'. classification='%s' words=%s images=%s tables=%s extractors=%s",
                        page_number,
                        file_path,
                        analysis.classification,
                        analysis.word_count,
                        analysis.image_count,
                        analysis.table_count,
                        ",".join(analysis.extractors),
                    )
                    extracted_text = self._extract_page_text(
                        fitz_module=fitz,
                        fitz_page=fitz_page,
                        plumber_page=plumber_page,
                        analysis=analysis,
                    )
                    logger.info(
                        "Page %s extraction completed for '%s'. extracted_chars=%s",
                        page_number,
                        file_path,
                        len(extracted_text),
                    )
                    extracted_pages.append(
                        ExtractedPDFPage(
                            page_number=page_number,
                            text=extracted_text,
                            analysis=analysis,
                        )
                    )
                logger.info("Completed PDF extraction workflow for '%s'. pages=%s", file_path, len(extracted_pages))
                return PDFExtractionResult(pages=extracted_pages)
            finally:
                if plumber_pdf is not None:
                    plumber_pdf.close()
        finally:
            document.close()

    def _analyze_page(self, fitz_page: Any, plumber_page: Any, page_number: int) -> PageAnalysis:
        raw_text = self._normalize_text(fitz_page.get_text("text"))
        word_count = len(raw_text.split()) if raw_text else 0
        image_count, image_area_ratio = self._analyze_images(fitz_page)
        meaningful_tables = self._extract_meaningful_tables(plumber_page)
        table_count = len(meaningful_tables)

        has_text = word_count >= settings.PDF_ANALYSIS_MIN_WORDS_FOR_TEXT
        has_tables = table_count > 0
        has_images = image_count > 0
        image_heavy = image_area_ratio >= settings.PDF_ANALYSIS_IMAGE_AREA_THRESHOLD
        ocr_heavy = image_area_ratio >= settings.PDF_ANALYSIS_OCR_IMAGE_AREA_THRESHOLD

        if has_text and has_tables and has_images and ocr_heavy:
            classification = "text_table_image"
            extractors = ("pymupdf", "pdfplumber", "ocr")
        elif has_text and has_tables:
            classification = "text_table"
            extractors = ("pymupdf", "pdfplumber")
        elif has_text and has_images and ocr_heavy:
            classification = "text_image"
            extractors = ("pymupdf", "ocr")
        elif has_text:
            classification = "text_only"
            extractors = ("pymupdf",)
        elif has_tables and has_images and ocr_heavy:
            classification = "image_table"
            extractors = ("pdfplumber", "ocr")
        elif has_tables:
            classification = "table_only"
            extractors = ("pdfplumber",)
        elif has_images and (ocr_heavy or image_heavy or word_count == 0):
            classification = "image_only"
            extractors = ("ocr",)
        else:
            classification = "text_only_fallback"
            extractors = ("pymupdf",)

        return PageAnalysis(
            page_number=page_number,
            word_count=word_count,
            image_count=image_count,
            image_area_ratio=image_area_ratio,
            table_count=table_count,
            classification=classification,
            extractors=extractors,
        )

    def _extract_page_text(
        self,
        fitz_module: Any,
        fitz_page: Any,
        plumber_page: Any,
        analysis: PageAnalysis,
    ) -> str:
        parts: list[str] = []

        if "pymupdf" in analysis.extractors:
            parts.append(self._normalize_text(fitz_page.get_text("text")))
        if "pdfplumber" in analysis.extractors:
            parts.append(self._extract_table_text(plumber_page))
        if "ocr" in analysis.extractors:
            parts.append(self._extract_ocr_text(fitz_module, fitz_page))

        merged_text = self._merge_text_parts(parts)
        if not merged_text:
            logger.warning(
                "No extractable content remained after processing page %s with classification '%s'.",
                analysis.page_number,
                analysis.classification,
            )
        return merged_text

    def _analyze_images(self, fitz_page: Any) -> tuple[int, float]:
        page_rect = fitz_page.rect
        page_area = max(page_rect.width * page_rect.height, 1)
        page_dict = fitz_page.get_text("dict")
        image_blocks = [block for block in page_dict.get("blocks", []) if block.get("type") == 1]
        image_area = 0.0
        for block in image_blocks:
            bbox = block.get("bbox")
            if not bbox or len(bbox) != 4:
                continue
            x0, y0, x1, y1 = bbox
            image_area += max(0.0, (x1 - x0) * (y1 - y0))
        return len(image_blocks), min(1.0, image_area / page_area)

    def _extract_meaningful_tables(self, plumber_page: Any) -> list[list[list[str]]]:
        if plumber_page is None:
            return []

        tables = plumber_page.extract_tables() or []
        meaningful_tables: list[list[list[str]]] = []
        for table in tables:
            normalized_rows = [
                [self._normalize_text(cell or "") for cell in row]
                for row in table
                if row is not None
            ]
            if not normalized_rows:
                continue

            row_count = len(normalized_rows)
            col_count = max((len(row) for row in normalized_rows), default=0)
            if row_count < settings.PDF_ANALYSIS_MIN_TABLE_ROWS or col_count < settings.PDF_ANALYSIS_MIN_TABLE_COLUMNS:
                continue

            total_cells = row_count * col_count
            non_empty_cells = sum(1 for row in normalized_rows for cell in row if cell)
            density = non_empty_cells / total_cells if total_cells else 0
            if density < settings.PDF_ANALYSIS_TABLE_DENSITY_THRESHOLD:
                continue
            meaningful_tables.append(normalized_rows)
        return meaningful_tables

    def _extract_table_text(self, plumber_page: Any) -> str:
        tables = self._extract_meaningful_tables(plumber_page)
        rendered_tables: list[str] = []
        for table in tables:
            rendered_rows = []
            for row in table:
                cleaned_cells = [cell for cell in row if cell]
                if cleaned_cells:
                    rendered_rows.append(" | ".join(cleaned_cells))
            if rendered_rows:
                rendered_tables.append("\n".join(rendered_rows))
        return "\n\n".join(rendered_tables)

    def _extract_ocr_text(self, fitz_module: Any, fitz_page: Any) -> str:
        pytesseract = self._load_module("pytesseract", feature_name="pytesseract OCR")
        pil_image_module = self._load_module("PIL.Image", feature_name="Pillow")

        pixmap = fitz_page.get_pixmap(matrix=fitz_module.Matrix(2, 2), alpha=False)
        image = pil_image_module.open(BytesIO(pixmap.tobytes("png")))
        try:
            try:
                return self._normalize_text(pytesseract.image_to_string(image))
            except pytesseract.TesseractNotFoundError as exc:
                raise HTTPException(
                    status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                    detail="Tesseract OCR is not available on the server",
                ) from exc
        finally:
            image.close()

    def _merge_text_parts(self, parts: list[str]) -> str:
        merged: list[str] = []
        seen: set[str] = set()
        for part in parts:
            normalized = self._normalize_text(part)
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            merged.append(normalized)
        return "\n\n".join(merged)

    def _open_pdfplumber(self, file_path: Path) -> Any | None:
        try:
            pdfplumber = importlib.import_module("pdfplumber")
        except ModuleNotFoundError:
            logger.warning("pdfplumber is not installed. Table analysis will be disabled.")
            return None
        return pdfplumber.open(file_path)

    def _load_module(self, module_name: str, feature_name: str) -> Any:
        try:
            return importlib.import_module(module_name)
        except ModuleNotFoundError as exc:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=f"{feature_name} is not available on the server",
            ) from exc

    def _normalize_text(self, value: str) -> str:
        compact_lines = re.sub(r"\n{3,}", "\n\n", value or "")
        compact_spaces = re.sub(r"[ \t]+", " ", compact_lines)
        return compact_spaces.strip()
