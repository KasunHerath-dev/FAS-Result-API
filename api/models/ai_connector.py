"""
AI Connector Module.
Connects to Google Gemini API using google-genai SDK to parse raw OCR result text
into structured FASResultPayload with dynamic Course Modules and Student Results (No GPA).
Includes an offline heuristic parser fallback when Gemini is unavailable.
"""

import os
import re
import logging
from typing import List, Optional, Tuple
from google import genai
from google.genai import errors, types
from pydantic import BaseModel, Field, ValidationError
from .table_ocr import GRADES, INDEX_PATTERN, GridPage
from .schemas import (
    FASResultPayload,
    CourseModuleCatalog,
    CourseModule,
    StudentRecord,
    CourseGrade,
    parse_student_index
)

logger = logging.getLogger(__name__)
COMBINATIONS = {"1": "I", "2": "II", "3": "III"}


class PageExtractionReport(BaseModel):
    page: int
    source: str
    table_rows: int | None = None
    extracted_rows: int
    warnings: list[str] = Field(default_factory=list)


class AIConnectorException(Exception):
    """Base exception for AI Connector errors."""
    pass


class AIConnector:
    """
    Communicates with Google Gemini API to structure raw OCR/digital text into
    two validated tables: Dynamic Course Modules and Student Results (Regular + Repeat).
    """

    DEFAULT_MODEL = "gemini-3.5-flash-lite"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: Optional[str] = None,
        allow_offline_fallback: bool = True,
        offline: bool = False,
    ):
        self.api_key = None if offline else api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = (
            (model_name or "").strip()
            or os.getenv("GEMINI_MODEL", "").strip()
            or self.DEFAULT_MODEL
        )
        self.allow_offline_fallback = allow_offline_fallback

        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key, http_options=types.HttpOptions(timeout=30000))
        elif not self.allow_offline_fallback:
            raise AIConnectorException("GEMINI_API_KEY must be provided or set in environment variables.")

        self.system_instruction = self._build_system_instruction()

    def _build_system_instruction(self) -> str:
        return (
            "You are an academic data parsing engine for the Faculty of Applied Sciences, Wayamba University of Sri Lanka.\n"
            "Your objective is to extract TWO distinct tables from the raw OCR result text:\n\n"
            "TABLE 1: DYNAMIC COURSE MODULE CATALOG\n"
            "- Extract Course Codes (e.g. CMIS2214, ELTN2213, MATH2213, STAT2212, ELPC 2220) and Course Titles from table headers.\n"
            "- CRITICAL: Course modules change dynamically for each Level, Semester, and Combination:\n"
            "  * Combination I has Electronics courses (ELTN).\n"
            "  * Combination III has Industrial Management courses (IMGT).\n"
            "  * Repeat section has the combined superset.\n"
            "  Instantiate a separate CourseModuleCatalog for each distinct (Level, Semester, Combination) block.\n\n"
            "TABLE 2: STUDENT RESULTS TABLE\n"
            "- Include every row, even when all of its grades are blank or hyphens.\n"
            "- Preserve the printed Index/Registration Number, including R, M, and R/M suffixes.\n"
            "- Map each grade to its own column. Omit a grade when its cell is blank, a hyphen, or unreadable.\n"
            "- STRICT REQUIREMENT: DO NOT extract or calculate GPA. FAS semester sheets have NO GPA column.\n"
            "- REPEAT & MEDICAL STUDENTS:\n"
            "  * Detect repeat sheets by header '-Repeat'.\n"
            "  * Parse raw index: '222002R' -> clean_index: '222002', student_type: 'Repeat', attempt: 2.\n"
            "  * '172149RRRRRR' -> clean_index: '172149', student_type: 'Repeat', attempt: 7.\n"
            "  * '222039M.' -> clean_index: '222039', student_type: 'Medical', attempt: 1.\n"
            "  * Read Combination from the 'COMB' column on repeat sheets.\n"
            "  * Ignore hyphens ('-') for courses the repeat student did not sit.\n\n"
            "VALID GRADES: A+, A, A-, B+, B, B-, C+, C, C-, D+, D, E, I (Incomplete), P (Pass - ELPC).\n"
            "Output strictly conforming to the FASResultPayload JSON schema."
        )

    def parse_with_gemini(self, text_chunk: str) -> FASResultPayload:
        """Sends a text chunk to Gemini and parses the structured response."""
        if not self.client:
            raise AIConnectorException("Gemini client is not initialized (missing API key).")

        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=text_chunk,
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instruction,
                    response_mime_type="application/json",
                    response_schema=FASResultPayload,
                )
            )
            if not response.text:
                raise AIConnectorException("Gemini returned no JSON text.")
            return FASResultPayload.model_validate_json(response.text)
        except ValidationError as ve:
            raise AIConnectorException("Gemini returned JSON that did not match the result schema.") from ve
        except AIConnectorException:
            raise
        except Exception as e:
            raise AIConnectorException("Gemini API request failed.") from e

    def parse_with_heuristics(self, text: str, is_repeat_default: bool = False) -> FASResultPayload:
        """
        High-precision rule-based parser as an offline fallback or pre-processor.
        Extracts course codes, titles, and student rows based on FAS layout patterns.
        """
        lines = [line.strip() for line in text.splitlines() if line.strip()]

        level = "Level 2"
        semester = "Semester II"
        academic_year = "2023/2024"
        combination = "Combination I"
        is_repeat_section = is_repeat_default

        # 1. Detect Header Metadata
        for line in lines[:15]:
            lvl_match = re.search(r"Level\s*(\d+)\s*Semester\s*([IVX]+)", line, re.IGNORECASE)
            if lvl_match:
                level = f"Level {lvl_match.group(1)}"
                semester = f"Semester {lvl_match.group(2)}"
            ay_match = re.search(r"Academic Year\s*([\d/]+)", line, re.IGNORECASE)
            if ay_match:
                academic_year = ay_match.group(1)
            if "Repeat" in line:
                is_repeat_section = True
            comb_match = re.search(r"Combination\s*([IVX\d]+)", line, re.IGNORECASE)
            if comb_match:
                combination = f"Combination {comb_match.group(1)}"

        # 2. Extract Course Codes from Header Line
        course_codes: List[str] = []
        code_pattern = re.compile(r"\b([A-Z]{3,4}\s*\d{4})\b")
        for line in lines[:25]:
            matches = code_pattern.findall(line)
            if len(matches) >= 3:
                course_codes = [re.sub(r"\s+", "", c) for c in matches]
                break

        # Standard known titles for L2S2 FAS courses
        known_titles = {
            "CMIS2214": "Data Structures & Analysis of Algorithms",
            "ELTN2213": "Semiconductor Devices",
            "ELTN2221": "Semiconductor Devices - Lab",
            "ELTN2232": "Analogue Electronics",
            "ELTN2241": "Design of Analogue Electronics - Lab Course I",
            "MATH2213": "Linear Algebra II",
            "STAT2212": "Design of Experiments",
            "STAT2222": "Regression Analysis",
            "IMGT2212": "Human Resource Management",
            "IMGT2222": "Operations Research",
            "ELPC2220": "English Language Proficiency Course II",
            "ELPC2120": "English Language Proficiency Course I",
        }

        modules = [
            CourseModule(course_code=code, title=known_titles.get(code.replace(" ", ""), f"Course Unit {code}"))
            for code in course_codes
        ]

        catalog = CourseModuleCatalog(
            level=level,
            semester=semester,
            combination=combination if not is_repeat_section else "All (Repeat)",
            modules=modules
        )

        # 3. Extract Student Result Rows
        student_records: List[StudentRecord] = []

        for line in lines:
            # Pattern matching a student row: e.g. "1  232004  B-  B-  A  B  C+ ..."
            # or in repeat: "1  1  222002R  -  -  -  -  C  - ..."
            tokens = re.split(r"[\s|]+", line)
            if len(tokens) < 2:
                continue

            # Look for student registration number (5 to 7 digits with optional repeat/medical suffix)
            reg_idx = -1
            raw_reg = ""
            for idx, token in enumerate(tokens[:5]):
                if INDEX_PATTERN.fullmatch(token):
                    reg_idx = idx
                    raw_reg = token
                    break

            if reg_idx == -1 or not raw_reg:
                continue

            # Check if repeat sheet with COMB column preceding reg number
            row_comb = combination
            if is_repeat_section and reg_idx >= 2:
                comb_num = tokens[0]
                if comb_num in COMBINATIONS:
                    row_comb = f"Combination {COMBINATIONS[comb_num]}"

            clean_id, s_type, attempt, _ = parse_student_index(raw_reg, is_repeat_section)
            remaining_tokens = tokens[reg_idx + 1:]

            # Map tokens to course grades
            student_grades: List[CourseGrade] = []
            grade_idx = 0
            for token in remaining_tokens:
                # Normalize token
                clean_tok = token.replace("Bt", "B+").replace("Cr", "C+").replace("At", "A+")
                if clean_tok in GRADES and grade_idx < len(course_codes):
                    student_grades.append(CourseGrade(
                        course_code=course_codes[grade_idx],
                        grade=clean_tok
                    ))
                    grade_idx += 1
                elif clean_tok == "-" and grade_idx < len(course_codes):
                    # Un-enrolled subject for repeat student; advance index but omit grade
                    grade_idx += 1

            if student_grades or is_repeat_section or (reg_idx > 0 and tokens[reg_idx - 1].isdecimal()):
                student_records.append(StudentRecord(
                    raw_index=raw_reg,
                    clean_index=clean_id,
                    combination=row_comb,
                    level=level,
                    semester=semester,
                    exam_type="Repeat" if is_repeat_section else "Regular",
                    student_type=s_type,
                    attempt=attempt,
                    results=student_grades
                ))

        return FASResultPayload(
            faculty="Faculty of Applied Sciences",
            university="Wayamba University of Sri Lanka",
            academic_year=academic_year,
            course_module_tables=[catalog] if modules else [],
            results_table=student_records
        )

    def process_text_stream(
        self, pages: List[Tuple[int, str, bool, str]], reports: list[PageExtractionReport] | None = None,
    ) -> FASResultPayload:
        """Process each page independently and preserve the source order of ruled rows."""
        catalogs: dict[tuple[str, str, str], dict[str, str]] = {}
        students: list[StudentRecord] = []
        academic_year = None
        combination = ""
        previous_serials: dict[tuple[str, str, str], int] = {}

        for page, mode, repeat, text in pages:
            warnings = []
            table_rows = None
            source = "offline text"
            if mode == "ocr-grid":
                grid = GridPage.model_validate_json(text)
                source = mode
                table_rows = len(grid.rows)
                warnings = grid.warnings
                detected = re.search(r"Combination\s*([IVX]+|\d+)\b", grid.heading, re.I)
                if detected:
                    value = detected[1].upper()
                    combination = f"Combination {COMBINATIONS.get(value, value)}"
                payload = self._parse_grid(grid, repeat, combination, previous_serials)
            else:
                offline = self.parse_with_heuristics(text, is_repeat_default=repeat)
                payload = offline
                if self.client:
                    try:
                        candidate = self.parse_with_gemini(f"[PAGE {page} | REPEAT: {repeat}]\n{text}")
                        known = {row.raw_index for row in offline.results_table}
                        returned = {row.raw_index for row in candidate.results_table}
                        if not candidate.results_table or not known.issubset(returned):
                            raise AIConnectorException("Gemini omitted rows recognized by local OCR.")
                        payload = candidate
                        source = "gemini"
                    except AIConnectorException as exc:
                        cause = exc.__cause__ or exc
                        reason = f"HTTP {cause.code}" if isinstance(cause, errors.APIError) else str(exc)
                        if not self.allow_offline_fallback:
                            raise AIConnectorException(f"Gemini failed on page {page}: {reason}") from exc
                        warnings.append(f"Gemini failed ({reason}); used offline text extraction.")
                if source == "offline text":
                    warnings.append("Plain-text extraction cannot verify row boundaries or grade alignment.")

            if payload.academic_year:
                academic_year = payload.academic_year
            for catalog in payload.course_module_tables:
                key = (catalog.level, catalog.semester, catalog.combination)
                courses = catalogs.setdefault(key, {})
                for module in catalog.modules:
                    courses.setdefault(module.course_code, module.title)
            students.extend(payload.results_table)
            if not payload.results_table:
                warnings.append("No student records were extracted from this page.")
            if reports is not None:
                reports.append(PageExtractionReport(
                    page=page, source=source, table_rows=table_rows,
                    extracted_rows=len(payload.results_table), warnings=warnings,
                ))
            logger.info("Page %d: %s, %d student rows, %d warnings", page, source, len(payload.results_table), len(warnings))

        return FASResultPayload(
            academic_year=academic_year,
            course_module_tables=[
                CourseModuleCatalog(
                    level=level, semester=semester, combination=cohort,
                    modules=[CourseModule(course_code=code, title=title) for code, title in modules.items()],
                )
                for (level, semester, cohort), modules in catalogs.items()
            ],
            results_table=students,
        )

    def _parse_grid(
        self, grid: GridPage, repeat: bool, combination: str,
        previous_serials: dict[tuple[str, str, str], int],
    ) -> FASResultPayload:
        period = re.search(r"Level\s*(\d+)\s+Semester\s*([IVXT1|\]]+)(?=\s)", grid.heading, re.I)
        year = re.search(r"Academic Year\s*(\d{4}\s*/\s*\d{4})", grid.heading, re.I)
        level = f"Level {period[1]}" if period else ""
        semester = f"Semester {period[2].upper().translate(str.maketrans('T1|]', 'IIII'))}" if period else ""
        cohort = "All (Repeat)" if repeat else combination
        if not period or not cohort:
            grid.warnings.append("The level, semester, or combination header could not be verified.")

        serial_key = (level, semester, cohort)
        previous_serial = previous_serials.get(serial_key, 0)
        students = []
        for row in grid.rows:
            expected = previous_serial + 1
            if row.serial != str(expected):
                grid.warnings.append(f"Expected serial {expected}, read {row.serial or '?'}.")
            previous_serial = int(row.serial) if row.serial.isdecimal() else expected
            raw_index = row.index if INDEX_PATTERN.fullmatch(row.index) else ""
            clean, student_type, attempt, _ = parse_student_index(raw_index, repeat)
            student_combination = combination
            if repeat:
                suffix = COMBINATIONS.get(row.combination)
                student_combination = f"Combination {suffix}" if suffix else ""
                if not suffix:
                    grid.warnings.append(f"Serial {row.serial}: unreadable combination.")
            students.append(StudentRecord(
                raw_index=row.index, clean_index=clean, combination=student_combination,
                level=level, semester=semester, student_type=student_type,
                exam_type="Repeat" if repeat else "Regular", attempt=attempt,
                results=[
                    CourseGrade(course_code=code, grade=grade)
                    for (code, _), grade in zip(grid.courses, row.grades, strict=True)
                    if grade
                ],
            ))
        previous_serials[serial_key] = previous_serial
        return FASResultPayload(
            academic_year=re.sub(r"\s+", "", year[1]) if year else None,
            course_module_tables=[CourseModuleCatalog(
                level=level, semester=semester, combination=cohort,
                modules=[CourseModule(course_code=code, title=title) for code, title in grid.courses],
            )],
            results_table=students,
        )
