"""
Pipeline Orchestrator Service.
Coordinates the end-to-end flow:
  PDFScrapper -> AIConnector -> FileExporter
"""

import time
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from pydantic import BaseModel, Field

from ..models.pdf_scrapper import PDFScrapper
from ..models.ai_connector import AIConnector
from ..models.file_export import FileExporter
from ..models.schemas import FASResultPayload

logger = logging.getLogger("fas_result_api")


class PipelineResult(BaseModel):
    success: bool
    document_path: str
    total_pages: int
    total_students: int
    regular_students: int
    repeat_students: int
    medical_students: int
    total_catalogs: int
    exported_files: Dict[str, str] = Field(default_factory=dict)
    execution_time_seconds: float
    error_message: Optional[str] = None


class PipelineOrchestrator:
    """
    Coordinates ingestion, extraction, structuring, and exporting of FAS result sheets.
    """

    def __init__(
        self,
        gemini_api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        output_dir: str | Path = "exports",
        temp_dir: Optional[str | Path] = None,
        ocr_dpi: int = 300,
        allow_offline_fallback: bool = True
    ):
        self.output_dir = Path(output_dir)
        self.temp_dir = Path(temp_dir) if temp_dir else None
        self.ocr_dpi = ocr_dpi
        self.ai_connector = AIConnector(
            api_key=gemini_api_key,
            model_name=model_name,
            allow_offline_fallback=allow_offline_fallback
        )
        self.file_exporter = FileExporter(output_dir=self.output_dir)

    def process_pdf(
        self,
        pdf_path: str | Path,
        base_export_name: Optional[str] = None
    ) -> PipelineResult:
        """
        Executes the 5-phase pipeline for the given PDF:
        1. Pre-flight check
        2. Stream extraction (PDFScrapper)
        3. Structuring into dual tables (AIConnector)
        4. Reconciliation & Repeat classification
        5. Exporting CSV files (FileExporter)
        """
        start_time = time.time()
        path = Path(pdf_path)

        if not path.exists():
            return PipelineResult(
                success=False,
                document_path=str(path),
                total_pages=0,
                total_students=0,
                regular_students=0,
                repeat_students=0,
                medical_students=0,
                total_catalogs=0,
                execution_time_seconds=0.0,
                error_message=f"File not found: {path}"
            )

        try:
            logger.info("Phase 1 & 2: Starting PDF extraction for %s", path.name)
            with PDFScrapper(
                pdf_path=path,
                temp_dir=self.temp_dir,
                ocr_dpi=self.ocr_dpi
            ) as scrapper:
                total_pages = scrapper.get_page_count()
                pages_data: List[tuple[int, str, bool, str]] = list(scrapper.stream_pages())

            logger.info("Phase 3: Parsing text into structured models for %d pages", len(pages_data))
            payload: FASResultPayload = self.ai_connector.process_text_stream(pages_data)

            # Phase 4: Cohort metrics calculation
            students = payload.results_table
            reg_count = sum(1 for s in students if s.student_type == "Regular")
            rep_count = sum(1 for s in students if s.student_type == "Repeat")
            med_count = sum(1 for s in students if s.student_type == "Medical")

            # Phase 5: Exporting CSV artifacts
            logger.info("Phase 5: Exporting dual-table CSV files")
            export_stem = base_export_name or path.stem.replace(" ", "_")
            export_paths = self.file_exporter.export_all(payload, base_name=export_stem)

            elapsed = round(time.time() - start_time, 2)
            logger.info("Pipeline completed successfully in %s seconds", elapsed)

            return PipelineResult(
                success=True,
                document_path=str(path),
                total_pages=total_pages,
                total_students=len(students),
                regular_students=reg_count,
                repeat_students=rep_count,
                medical_students=med_count,
                total_catalogs=len(payload.course_module_tables),
                exported_files={k: str(v) for k, v in export_paths.items()},
                execution_time_seconds=elapsed
            )

        except Exception as e:
            logger.exception("Pipeline failed with exception")
            elapsed = round(time.time() - start_time, 2)
            return PipelineResult(
                success=False,
                document_path=str(path),
                total_pages=0,
                total_students=0,
                regular_students=0,
                repeat_students=0,
                medical_students=0,
                total_catalogs=0,
                execution_time_seconds=elapsed,
                error_message=str(e)
            )
