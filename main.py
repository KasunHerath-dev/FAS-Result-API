"""
FAS Result API - Entry Point and CLI.
Provides CLI commands to process result PDFs or launch the FastAPI server.
"""

import sys
import argparse
import logging
from pathlib import Path
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger("fas_main")


def run_server(host: str = "0.0.0.0", port: int = 8000, reload: bool = False):
    """Starts the FastAPI development server."""
    import uvicorn
    logger.info("Starting FAS Result API server on http://%s:%d", host, port)
    uvicorn.run("api.app:app", host=host, port=port, reload=reload)


def process_pdf_cli(
    pdf_path: str,
    output_dir: str = "exports",
    model_name: str | None = None,
    ocr_dpi: int = 300,
    offline: bool = False,
    review_file: str | None = None,
):
    """Executes the extraction and export pipeline on a target PDF."""
    from api.services.orchestrator import PipelineOrchestrator

    path = Path(pdf_path)
    if not path.exists():
        logger.error("Specified PDF does not exist: %s", path)
        sys.exit(1)

    logger.info("Processing FAS result document: %s", path)
    orchestrator = PipelineOrchestrator(
        output_dir=output_dir,
        model_name=model_name,
        ocr_dpi=ocr_dpi,
        allow_offline_fallback=True,
        offline=offline,
    )

    result = orchestrator.process_pdf(path, review_file=review_file)

    if result.success:
        print("\n" + "=" * 60)
        print("EXTRACTION & EXPORT SUMMARY")
        print("=" * 60)
        print(f"Document:          {result.document_path}")
        print(f"Total Pages:       {result.total_pages}")
        print(f"Total Students:    {result.total_students}")
        print(f" - Regular:        {result.regular_students}")
        print(f" - Repeat:         {result.repeat_students}")
        print(f" - Medical:        {result.medical_students}")
        print(f"Course Catalogs:   {result.total_catalogs}")
        print(f"Execution Time:    {result.execution_time_seconds}s")
        print("\nGenerated CSV Files:")
        for name, file_path in result.exported_files.items():
            print(f"  * {name:15}: {file_path}")
        warnings = [(page.page, warning) for page in result.pages for warning in page.warnings]
        if warnings:
            print(f"\nExtraction warnings ({len(warnings)}):")
            for page, warning in warnings:
                print(f"  * Page {page}: {warning}")
        print("=" * 60 + "\n")
    else:
        logger.error("Pipeline failed: %s", result.error_message)
        sys.exit(1)


def inspect_pdf_cli(pdf_path: str):
    """Quickly inspects a PDF for page count, scan layer, and repeat section indicators."""
    from api.models.pdf_scrapper import PDFScrapper

    path = Path(pdf_path)
    if not path.exists():
        logger.error("File not found: %s", path)
        sys.exit(1)

    with PDFScrapper(path) as scrapper:
        pages = scrapper.get_page_count()
        print(f"\nDocument: {path.name} | Total Pages: {pages}")
        print("-" * 50)
        for page_num, mode, is_repeat, text in scrapper.stream_pages():
            sec_type = "REPEAT SECTION" if is_repeat else "REGULAR SECTION"
            chars = len(text.strip())
            print(f"Page {page_num:02d}: Mode={mode.upper():6} | Chars={chars:5} | Section={sec_type}")


def main():
    parser = argparse.ArgumentParser(
        prog="fas-result-api",
        description="FAS Result API - Academic Result Processing & CSV Export Engine"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available sub-commands")

    # Command: serve
    serve_parser = subparsers.add_parser("serve", help="Start the FastAPI HTTP server")
    serve_parser.add_argument("--host", default="0.0.0.0", help="Binding host (default: 0.0.0.0)")
    serve_parser.add_argument("--port", type=int, default=8000, help="Port (default: 8000)")
    serve_parser.add_argument("--reload", action="store_true", help="Enable auto-reload for dev")

    # Command: process
    proc_parser = subparsers.add_parser("process", help="Process a PDF file and export CSVs")
    proc_parser.add_argument("pdf_path", help="Path to the FAS result PDF file")
    proc_parser.add_argument("-o", "--output-dir", default="exports", help="Export output directory")
    proc_parser.add_argument("-m", "--model", default=None, help="Gemini model name")
    proc_parser.add_argument("--dpi", type=int, default=300, help="DPI for scanning (default: 300)")
    proc_parser.add_argument("--offline", action="store_true", help="Process locally without Gemini")
    proc_parser.add_argument("--review", help="JSON file with reviewed OCR cells for this PDF")

    # Command: inspect
    insp_parser = subparsers.add_parser("inspect", help="Inspect PDF pages and detection modes")
    insp_parser.add_argument("pdf_path", help="Path to the PDF file")

    args = parser.parse_args()

    if args.command == "serve":
        run_server(host=args.host, port=args.port, reload=args.reload)
    elif args.command == "process":
        process_pdf_cli(
            pdf_path=args.pdf_path,
            output_dir=args.output_dir,
            model_name=args.model,
            ocr_dpi=args.dpi,
            offline=args.offline,
            review_file=args.review,
        )
    elif args.command == "inspect":
        inspect_pdf_cli(args.pdf_path)
    else:
        # Default behavior if run without args: inspect or process sample PDF if present
        sample_pdf = Path("docs/L2S2-Results-Ac.-2023-2024.pdf")
        if sample_pdf.exists():
            print(f"No command specified. Running demo processing on: {sample_pdf}\n")
            process_pdf_cli(str(sample_pdf))
        else:
            parser.print_help()


if __name__ == "__main__":
    main()
