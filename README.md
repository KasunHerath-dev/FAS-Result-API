# FAS Result API

An automated, memory-efficient data extraction, AI structuring, and tabular export engine designed for academic examination result sheets from the **Faculty of Applied Sciences (FAS)** (e.g., Wayamba University of Sri Lanka).

---

## Features

- **Hybrid PDF Extraction Engine (`PDFScrapper`)**:
  - Handles scanned landscape photocopies (Canon iR2925) and digital vector PDFs.
  - Page-by-page generator streaming with low memory footprint (near-zero RAM accumulation).
  - Tesseract OCR integration with automatic landscape orientation detection.
- **AI Structuring & Normalization (`AIConnector`)**:
  - Powered by Google Gemini (`google-genai` SDK) with deterministic JSON Schema output (`FASResultPayload`).
  - Includes a built-in offline heuristic extractor fallback for local environments without API keys.
- **Dual-Table Architecture**:
  1. **Course Module Table (Dynamic Master Catalog)**: Captures **Course Code** and **Course Title**, dynamically varying for each **Level**, **Semester**, and **Combination**.
  2. **Student Results Table (Transactional Mark Sheet)**: Captures student marks with **Clean Index Number**, **Raw Index Number**, **Combination**, **Level**, **Semester**, **Exam Type**, **Student Type**, **Attempt Count**, and **Course Unit Grades**.
- **No GPA Column**: Adheres strictly to official FAS semester result sheets which do not compute or publish GPA.
- **Repeat & Medical Students**:
  - Automatically identifies Repeat Examination sections (`-Repeat`).
  - Calculates sitting attempt numbers from suffix markers (e.g., `222002R` $\to$ Attempt 2; `172149RRRRRR` $\to$ Attempt 7).
  - Detects medical excuses (e.g., `222039M.` $\to$ Medical, Attempt 1).
  - Handles sparse student rows (un-enrolled courses output as `-`).
- **Excel-Compatible CSV Export (`FileExporter`)**:
  - Exports **Wide Format** (pivoted matrix) and **Long Format** (normalized relational).
  - Encoded with `utf-8-sig` (UTF-8 with BOM) for clean display in Microsoft Excel.
  - Atomic file writing (`.tmp` then `os.replace`) prevents file corruption.
- **FastAPI HTTP Service & CLI**:
  - Launch a REST API with interactive Swagger documentation (`/docs`).
  - Process PDFs or inspect pages directly via command line.

---

## Directory Structure

```
FAS Result API/
├── api/
│   ├── app.py                  # FastAPI web application
│   ├── models/
│   │   ├── schemas.py          # Pydantic schemas (FASResultPayload, StudentRecord, etc.)
│   │   ├── pdf_scrapper.py     # PDF text & OCR extraction engine
│   │   ├── ai_connector.py     # Gemini AI & offline heuristic parser
│   │   └── file_export.py      # Dual-table CSV exporter (Wide & Long)
│   └── services/
│       └── orchestrator.py     # End-to-end pipeline coordinator
├── docs/
│   ├── 01 - pdf scrapper.md    # Extraction specification
│   ├── 02 - ai connect.md       # AI structuring specification
│   ├── 03 - file export.md      # CSV export specification
│   ├── 04 - bussinas logic.md   # Business logic & system architecture
│   └── L2S2-Results-Ac.-2023-2024.pdf  # Sample FAS examination PDF
├── tests/                      # Pytest test suite (12 passing tests)
├── exports/                    # Generated CSV export files
├── main.py                     # CLI & server entrypoint
├── pyproject.toml              # Project dependencies & metadata
└── .env.example                # Configuration template
```

---

## Installation & Setup

### Prerequisites
* Python $\ge 3.10$
* System packages: `tesseract-ocr` and `poppler-utils`
  ```bash
  sudo apt install tesseract-ocr poppler-utils
  ```
* [uv](https://docs.astral.sh/uv/) package manager (recommended) or standard `pip`

### Install Dependencies
```bash
uv sync
```

### Environment Configuration
Copy `.env.example` to `.env` and set your Gemini API key (optional for online AI extraction):
```bash
cp .env.example .env
```
Edit `.env`:
```env
GEMINI_API_KEY=your_gemini_api_key_here
```
*(Note: If no API key is provided, the system seamlessly uses the offline heuristic parser).*

---

## Usage

### 1. Command Line Interface (CLI)

#### Process a PDF and generate CSVs:
```bash
uv run python main.py process "docs/L2S2-Results-Ac.-2023-2024.pdf" -o exports
```

#### Inspect a PDF (page count, scan mode, repeat sections):
```bash
uv run python main.py inspect "docs/L2S2-Results-Ac.-2023-2024.pdf"
```

#### Launch the FastAPI server:
```bash
uv run python main.py serve --port 8000 --reload
```

---

### 2. REST API Endpoints

Once the server is running on `http://localhost:8000`:
* Interactive API Documentation: [http://localhost:8000/docs](http://localhost:8000/docs)
* Health Check: `GET /`
* Upload & Process PDF: `POST /api/v1/extract-results`
  - Form field `file`: PDF file binary
  - Response: JSON summary with student metrics and generated CSV file paths
* Download Exported CSV: `GET /api/v1/download/{filename}`

---

## Running Tests

Run the comprehensive unit and integration test suite:
```bash
uv run pytest
```
All 12 tests cover:
- Repeat index and attempt parsing (`222002R`, `172149RRRRRR`, `222039M.`)
- Absence of GPA across all records and CSV headers
- Dynamic course module catalog generation
- Multi-format CSV export (Wide and Long) with UTF-8 BOM encoding
- PDF scrapper orientation and OCR streaming
- FastAPI HTTP endpoints
