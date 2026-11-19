# FAS Result API

An automated, memory-efficient data extraction, AI structuring, and tabular export engine designed for academic examination result sheets from the **Faculty of Applied Sciences (FAS)** (e.g., Wayamba University of Sri Lanka).

---

## Features

- **Hybrid PDF Extraction Engine (`PDFScrapper`)**:
  - Handles scanned landscape photocopies (Canon iR2925) and digital vector PDFs.
  - Renders one page at a time and reads ruled result sheets by table cell.
  - Tesseract OCR preserves empty cells, repeat indexes, and grade positions. Page reports flag unreadable or conflicting cells.
- **AI Structuring & Normalization (`AIConnector`)**:
  - Parses ruled tables locally. Gemini can structure pages that use the text extraction path.
  - Includes an offline text parser when Gemini is disabled or unavailable.
- **Dual-Table Architecture**:
  1. **Course Module Table (Dynamic Master Catalog)**: Captures **Course Code** and **Course Title** for each **Academic Year**, **Level**, **Semester**, and **Combination**.
  2. **Student Results Table (Transactional Mark Sheet)**: CSV exports keep the printed registration number and any repeat or medical suffix in **Index**. **Base_Index** contains the registration digits, including leading zeros. The table also includes **Combination**, **Academic Year**, **Level**, **Semester**, **Exam Type**, **Student Type**, **Attempt Count**, and **Course Unit Grades**.
- **No GPA Column**: Adheres strictly to official FAS semester result sheets which do not compute or publish GPA.
- **Repeat & Medical Students**:
  - Automatically identifies Repeat Examination sections (`-Repeat`).
  - Calculates sitting attempt numbers from suffix markers (e.g., `222002R` $\to$ Attempt 2; `172149RRRRRR` $\to$ Attempt 7).
  - Detects medical excuses (e.g., `222039M.` $\to$ Medical, Attempt 1).
  - Handles sparse student rows. Unenrolled courses appear as empty cells in the Wide CSV.
- **Excel-Compatible CSV Export (`FileExporter`)**:
  - Exports **Wide Format** (pivoted matrix) and **Long Format** (normalized relational).
  - Encoded with `utf-8-sig` (UTF-8 with BOM) for clean display in Microsoft Excel.
  - Writes each CSV to a unique temporary file in the output directory, then publishes it with `os.replace`.
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
├── docs/                       # Optional local notes and sample PDFs (gitignored)
├── exports/                    # Generated CSV files (gitignored)
├── main.py                     # CLI & server entrypoint
├── pyproject.toml              # Project dependencies & metadata
└── .env.example                # Configuration template
```

---

## Installation & Setup

### Prerequisites
* Python $\ge 3.14$
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
GEMINI_MODEL=gemini-3.5-flash-lite
```

`GEMINI_MODEL` is optional and defaults to `gemini-3.5-flash-lite`. The CLI `--model` option or HTTP `model_name` form field takes precedence. If Gemini is configured, pages that use text extraction may send their text to Google. Use `--offline` or the HTTP field `offline=true` for local-only processing.

---

## Usage

### 1. Command Line Interface (CLI)

#### Process a PDF and generate CSVs:
```bash
uv run python main.py process /path/to/results.pdf -o exports
```

The app looks for a matching `<pdf-stem>-review.json` beside the PDF or in the project's `docs/` directory. To select a specific review file, pass `--review`.

```bash
uv run python main.py process /path/to/results.pdf --offline --review /path/to/review.json -o exports
```

The review JSON has a `source_sha256` string, a `page_rows` array with the row count for each page, and a `cells` array. Each cell has a one-based `page` and `row`, a `column` (course code, `index`, `serial`, or `combination`), and a verified string `value`. The app checks the PDF fingerprint and the detected row counts before applying it.

If an export has `UNREAD`, use the page, table row, and course code in the extraction warning to find the cell in the PDF. Put the grade you can verify from that cell in the review JSON and export again. Use a clearer scan if the original grade is illegible.

#### Inspect a PDF (page count, scan mode, repeat sections):
```bash
uv run python main.py inspect /path/to/results.pdf
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
  - Optional form field `base_export_name`: Override the CSV filename prefix.
  - Optional form field `offline`: Set to `true` for local-only processing.
  - Optional file field `review`: Upload the cell review JSON for the PDF.
  - Response: JSON summary with the academic year when shared by the document, student metrics, generated CSV file paths, and per-page row counts and warnings.
* Download Exported CSV: `GET /api/v1/download/{filename}`

---

## CSV Output

All three CSVs include `Academic_Year`, `Level`, and `Semester`. The academic year comes from the result heading. Each recognised period stays on its own rows when a PDF covers multiple periods.

By default, the filename starts with the academic year, level, and semester, followed by the original PDF stem. Processing `results.pdf` for academic year 2023/2024, Level 2, Semester II writes these files.

| File | Contents |
| --- | --- |
| `AY-2023-2024_Level-2_Semester-II_results_modules.csv` | One row per module in each academic year, level, semester, and combination catalog. |
| `AY-2023-2024_Level-2_Semester-II_results_results_wide.csv` | One row per student record. Course columns come from the catalogs and the extracted grades. Unenrolled courses and blank cells stay empty. A visible grade the OCR could not read appears as `UNREAD`. |
| `AY-2023-2024_Level-2_Semester-II_results_results_long.csv` | One row per extracted course grade. Empty cells and unreadable placeholders are omitted. |

Exports with incomplete or mixed periods include a PDF fingerprint in the default filename. Unidentified academic years stay empty in the CSV if the year cannot be shared across the document. The API's explicit `base_export_name` still sets the filename prefix.

A successful export confirms that the pipeline wrote its parsed data. Check the
student count and grades against the source PDF, especially after offline
fallback or when processing a scanned result sheet.

## Tests

```bash
uv run pytest
```
