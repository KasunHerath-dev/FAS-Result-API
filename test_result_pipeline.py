import csv
import hashlib
from types import SimpleNamespace

import pytest

from api.models.ai_connector import AIConnector
from api.models.file_export import FileExporter
from api.models.ocr_review import OCRReview
from api.models.schemas import FASResultPayload
from api.models.table_ocr import GridPage, GridRow
from api.services import orchestrator


def grid(heading, rows, repeat=False, courses=None, warnings=None):
    return GridPage(
        heading=heading,
        repeat=repeat,
        courses=courses or [("TEST1234", "Test"), ("TEST1235", "Another test")],
        rows=[GridRow(**row) for row in rows],
        warnings=warnings or [],
    )


def page(number, table):
    return number, "ocr-grid", table.repeat, table.model_dump_json()


def read_csv(path):
    with path.open(encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def test_grid_keeps_missing_cells_and_every_sitting(tmp_path):
    regular = grid("Level 2 Semester II Combination I", [
        dict(serial="1", index="000001", grades=["", "C+"]),
        dict(serial="2", index="000002", grades=["", ""]),
    ])
    repeat = grid("Level 2 Semester IT Repeat", [
        dict(serial="1", index="000001RR/M", combination="3", grades=["I", ""]),
    ], repeat=True)
    reports = []
    connector = AIConnector(offline=True)

    payload = connector.process_text_stream([page(1, regular), page(2, repeat)], reports)
    paths = FileExporter(tmp_path).export_all(payload)
    wide = read_csv(paths["results_wide"])
    long = read_csv(paths["results_long"])

    assert len(wide) == 3
    assert wide[0]["TEST1234"] == wide[1]["TEST1235"] == wide[2]["TEST1235"] == ""
    assert wide[0]["TEST1235"] == "C+"
    assert wide[2]["Index"] == "000001RR/M"
    assert long[1]["Index"] == "000001RR/M"
    assert wide[0]["Base_Index"] == wide[2]["Base_Index"] == "000001"
    assert long[0]["Base_Index"] == long[1]["Base_Index"] == "000001"
    assert "Raw_Index" not in wide[0] and "Raw_Index" not in long[0]
    assert wide[2]["Student_Type"] == "Medical"
    assert wide[2]["Attempt"] == "3"
    assert wide[2]["Semester"] == "Semester II"
    assert wide[0]["Academic_Year"] == ""
    assert [(row["Course_Code"], row["Grade"]) for row in long] == [("TEST1235", "C+"), ("TEST1234", "I")]
    assert [report.table_rows for report in reports] == [2, 1]
    assert not any(report.warnings for report in reports)


def test_review_replaces_the_cell_and_clears_its_warning():
    table = grid("Level 2 Semester II Combination I", [
        dict(serial="1", index="000001", grades=["UNREAD", "B"]),
    ], warnings=["Serial 1, TEST1234: review grade (?/?/?)"])
    review = OCRReview(source_sha256="irrelevant for this unit test", page_rows=[1], cells=[{
        "page": 1, "row": 1, "column": "TEST1234", "value": "C-",
    }])

    updated = GridPage.model_validate_json(review.apply([page(1, table)])[0][3])
    assert updated.rows[0].grades == ["C-", "B"]
    assert updated.warnings == []

    review.page_rows = [2]
    with pytest.raises(ValueError, match="counts changed"):
        review.apply([page(1, table)])


def test_default_review_applies_only_to_matching_pdf(tmp_path):
    pdf = tmp_path / "results.pdf"
    pdf.write_bytes(b"the exact scanned document")
    docs = tmp_path / "docs"
    docs.mkdir()
    review_file = docs / "results-review.json"
    review = OCRReview(source_sha256=hashlib.sha256(pdf.read_bytes()).hexdigest(), page_rows=[], cells=[])
    review_file.write_text(review.model_dump_json(), encoding="utf-8")

    assert OCRReview.find_for_pdf(pdf, docs) == review
    pdf.write_bytes(b"a different scan with the same filename")
    assert OCRReview.find_for_pdf(pdf, docs) is None
    with pytest.raises(ValueError, match="different PDF"):
        OCRReview.for_pdf(review_file, pdf)


def test_gemini_valid_json_and_incomplete_page_fallback():
    connector = AIConnector(offline=True)
    text = "Level 2 Semester II Combination I\nTEST1234 TEST1235 TEST1236\n1 000001 A - B\n2 000002"
    local = connector.parse_with_heuristics(text)
    response = [local.model_dump_json()]

    def generate_content(**kwargs):
        assert kwargs["config"].response_mime_type == "application/json"
        assert kwargs["model"] == connector.model_name
        return SimpleNamespace(text=response[0])

    connector.client = SimpleNamespace(models=SimpleNamespace(generate_content=generate_content))
    reports = []
    parsed = connector.process_text_stream([(1, "native", False, text)], reports)
    assert len(parsed.results_table) == 2
    assert reports[0].source == "gemini"

    response[0] = FASResultPayload(results_table=local.results_table[:1]).model_dump_json()
    reports.clear()
    parsed = connector.process_text_stream([(1, "native", False, text)], reports)
    assert len(parsed.results_table) == 2
    assert reports[0].source == "offline text"
    assert "omitted rows" in reports[0].warnings[0]


def test_next_batch_with_same_pdf_name_gets_its_own_exports(tmp_path, monkeypatch):
    pdf = tmp_path / "results.pdf"
    output = tmp_path / "exports"

    class Scrapper:
        def __init__(self, pdf_path, **kwargs):
            self.heading = pdf_path.read_text()

        def __enter__(self):
            return self

        def __exit__(self, *exception):
            pass

        def get_page_count(self):
            return 1

        def stream_pages(self):
            yield page(1, grid(self.heading, [dict(serial="1", index="000001", grades=["A", ""])]))

    monkeypatch.setattr(orchestrator, "PDFScrapper", Scrapper)
    pipeline = orchestrator.PipelineOrchestrator(offline=True, output_dir=output)
    for year in ("2023/2024", "2024/2025"):
        pdf.write_text(f"Level 2 Semester 2 (Academic Year: {year}) Combination I")
        result = pipeline.process_pdf(pdf)
        assert result.success, result.error_message
        assert result.academic_year == year
        assert all(f"AY-{year.replace('/', '-')}_Level-2_Semester-II_results_" in path
                   for path in result.exported_files.values())
        for path in output.glob(f"AY-{year.replace('/', '-')}_*.csv"):
            assert {row["Academic_Year"] for row in read_csv(path)} == {year}
    assert len(list(output.glob("*.csv"))) == 6


def test_combined_pdf_preserves_academic_year_per_page(tmp_path):
    pages = []
    for number, year in enumerate(("2023/2024", "2024-25"), 1):
        heading = f"Level 3 Semester I (Academic Year {year}) Combination I"
        pages.append(page(number, grid(heading, [dict(serial="1", index="000001", grades=["A", ""])])))
    payload = AIConnector(offline=True).process_text_stream(pages)
    paths = FileExporter(tmp_path).export_all(payload)

    assert payload.academic_year is None
    for table in ("course_modules", "results_wide", "results_long"):
        assert {row["Academic_Year"] for row in read_csv(paths[table])} == {"2023/2024", "2024/2025"}
