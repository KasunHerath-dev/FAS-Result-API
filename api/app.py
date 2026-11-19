"""
FastAPI Application for FAS Result API.
Exposes endpoints for PDF upload, automated processing, and CSV downloads.
"""

import shutil
import tempfile
from pathlib import Path
from typing import Optional
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

from .services.orchestrator import PipelineOrchestrator, PipelineResult

load_dotenv()

app = FastAPI(
    title="FAS Result API",
    description="Automated Extraction & Processing Engine for Faculty of Applied Sciences (FAS) Examination Results",
    version="0.1.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

EXPORTS_DIR = Path("exports")
EXPORTS_DIR.mkdir(parents=True, exist_ok=True)


@app.get("/", tags=["Health"])
def root():
    return {
        "status": "online",
        "service": "FAS Result API",
        "version": "0.1.0",
        "endpoints": {
            "extract_results": "POST /api/v1/extract-results",
            "download_csv": "GET /api/v1/download/{filename}",
            "docs": "/docs"
        }
    }


@app.post("/api/v1/extract-results", tags=["Extraction"], response_model=PipelineResult)
async def extract_results(
    file: UploadFile = File(..., description="FAS Result PDF file to process"),
    model_name: Optional[str] = Form(default=None, description="Overrides the configured Gemini model"),
    ocr_dpi: int = Form(default=300, description="DPI for scanning pages (default: 300)"),
    base_export_name: Optional[str] = Form(default=None, description="Custom prefix for exported CSVs"),
    offline: bool = Form(default=False, description="Process the PDF locally without Gemini"),
    review: Optional[UploadFile] = File(default=None, description="JSON file with reviewed OCR cells for this PDF"),
):
    """
    Ingests an academic result PDF, executes the hybrid extraction and AI structuring pipeline,
    and returns processing metrics along with paths to the exported CSV tables.
    """
    if not file.filename or not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    if base_export_name and ("/" in base_export_name or "\\" in base_export_name):
        raise HTTPException(status_code=400, detail="Export prefix must be a single filename prefix.")

    temp_dir = Path(tempfile.mkdtemp(prefix="fas_upload_"))
    uploaded_pdf_path = temp_dir / Path(file.filename.replace("\\", "/")).name

    try:
        # Save uploaded file
        with open(uploaded_pdf_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
        review_path = None
        if review is not None:
            review_path = temp_dir / "ocr-review.json"
            with review_path.open("wb") as buffer:
                shutil.copyfileobj(review.file, buffer)

        # Initialize orchestrator
        orchestrator = PipelineOrchestrator(
            model_name=model_name,
            output_dir=EXPORTS_DIR,
            ocr_dpi=ocr_dpi,
            allow_offline_fallback=True,
            offline=offline,
        )

        stem = base_export_name or uploaded_pdf_path.stem
        result = orchestrator.process_pdf(uploaded_pdf_path, base_export_name=stem, review_file=review_path)

        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_message or "Extraction failed.")

        return result

    finally:
        # Cleanup uploaded temporary PDF
        try:
            if uploaded_pdf_path.exists():
                uploaded_pdf_path.unlink()
            if temp_dir.exists():
                shutil.rmtree(temp_dir, ignore_errors=True)
        except Exception:
            pass


@app.get("/api/v1/download/{filename}", tags=["Export"])
def download_file(filename: str):
    """Downloads a generated CSV file from the exports directory."""
    # Sanitize path to prevent directory traversal
    safe_name = Path(filename).name
    file_path = EXPORTS_DIR / safe_name

    if file_path.suffix.lower() != ".csv" or file_path.is_symlink() or not file_path.is_file():
        raise HTTPException(status_code=404, detail=f"Export file '{safe_name}' not found.")

    return FileResponse(
        path=file_path,
        media_type="text/csv",
        filename=safe_name
    )
