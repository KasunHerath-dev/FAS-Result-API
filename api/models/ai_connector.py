"""
AI Connector Module.
Connects to Google Gemini API using google-genai SDK to parse raw OCR result text
into structured FASResultPayload with dynamic Course Modules and Student Results (No GPA).
Includes an offline heuristic parser fallback when Gemini is unavailable.
"""

import os
import re
import json
import logging
from typing import List, Optional, Tuple, Dict
from google import genai
from google.genai import errors, types
from pydantic import ValidationError
from .schemas import (
    FASResultPayload,
    CourseModuleCatalog,
    CourseModule,
    StudentRecord,
    CourseGrade,
    parse_student_index
)

logger = logging.getLogger(__name__)


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
        allow_offline_fallback: bool = True
    ):
        self.api_key = api_key or os.getenv("GEMINI_API_KEY")
        self.model_name = (
            (model_name or "").strip()
            or os.getenv("GEMINI_MODEL", "").strip()
            or self.DEFAULT_MODEL
        )
        self.allow_offline_fallback = allow_offline_fallback

        self.client = None
        if self.api_key:
            self.client = genai.Client(api_key=self.api_key)
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
            "- Extract each student's Serial No, Index/Registration Number, and course grades.\n"
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
            return FASResultPayload.model_validate_json(response.text)
        except ValidationError as ve:
            raise AIConnectorException(f"Schema validation error: {ve}") from ve
        except Exception as e:
            raise AIConnectorException(f"Gemini API invocation error: {e}") from e

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
                course_codes = [re.sub(r"\s+", " ", c).strip() for c in matches]
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
            "ELPC 2220": "English Language Proficiency Course II",
            "ELPC 2120": "English Language Proficiency Course I",
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
        valid_grades = {"A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "E", "I", "P", "MC", "AB", "WH", "NE"}

        for line in lines:
            # Pattern matching a student row: e.g. "1  232004  B-  B-  A  B  C+ ..."
            # or in repeat: "1  1  222002R  -  -  -  -  C  - ..."
            tokens = re.split(r"[\s|]+", line)
            if len(tokens) < 3:
                continue

            # Look for student registration number (5 to 7 digits with optional repeat/medical suffix)
            reg_idx = -1
            raw_reg = ""
            for idx, token in enumerate(tokens[:5]):
                if re.match(r"^\d{5,6}[A-Za-z\.]*$", token):
                    reg_idx = idx
                    raw_reg = token
                    break

            if reg_idx == -1 or not raw_reg:
                continue

            # Check if repeat sheet with COMB column preceding reg number
            row_comb = combination
            if is_repeat_section and reg_idx >= 2:
                comb_num = tokens[0]
                if comb_num in ["1", "2", "3"]:
                    row_comb = f"Combination {comb_num}"

            clean_id, s_type, attempt, _ = parse_student_index(raw_reg, is_repeat_section)
            remaining_tokens = tokens[reg_idx + 1:]

            # Map tokens to course grades
            student_grades: List[CourseGrade] = []
            grade_idx = 0
            for token in remaining_tokens:
                # Normalize token
                clean_tok = token.replace("Bt", "B+").replace("Cr", "C+").replace("At", "A+")
                if clean_tok in valid_grades and grade_idx < len(course_codes):
                    student_grades.append(CourseGrade(
                        course_code=course_codes[grade_idx],
                        grade=clean_tok
                    ))
                    grade_idx += 1
                elif clean_tok == "-" and grade_idx < len(course_codes):
                    # Un-enrolled subject for repeat student; advance index but omit grade
                    grade_idx += 1

            if student_grades or is_repeat_section:
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

    def process_text_stream(self, pages: List[Tuple[int, str, bool, str]]) -> FASResultPayload:
        """
        Processes multi-page text blocks.
        If Gemini client is active, chunks text and queries Gemini API.
        Otherwise, falls back to the high-precision heuristic extractor.
        """
        all_catalogs: List[CourseModuleCatalog] = []
        all_students: List[StudentRecord] = []
        faculty = "Faculty of Applied Sciences"
        university = "Wayamba University of Sri Lanka"
        academic_year = "2023/2024"

        # Chunk pages in batches of 2-3 pages
        chunk_size = 3
        for i in range(0, len(pages), chunk_size):
            chunk = pages[i:i + chunk_size]
            chunk_text = "\n\n".join([f"[PAGE {p[0]} | REPEAT: {p[2]}]\n{p[3]}" for p in chunk])
            is_repeat_chunk = any(p[2] for p in chunk)

            if self.client:
                try:
                    payload = self.parse_with_gemini(chunk_text)
                except Exception as exc:
                    if not self.allow_offline_fallback:
                        raise
                    cause = exc.__cause__ or exc
                    reason = f"HTTP {cause.code}" if isinstance(cause, errors.APIError) else type(cause).__name__
                    logger.warning(
                        "Gemini model %s failed for pages %d–%d (%s). Using offline heuristics.",
                        self.model_name, chunk[0][0], chunk[-1][0], reason,
                    )
                    payload = self.parse_with_heuristics(chunk_text, is_repeat_default=is_repeat_chunk)
            else:
                payload = self.parse_with_heuristics(chunk_text, is_repeat_default=is_repeat_chunk)

            if payload.academic_year:
                academic_year = payload.academic_year
            all_catalogs.extend(payload.course_module_tables)
            all_students.extend(payload.results_table)

        # Deduplicate course module catalogs by (level, semester, combination)
        merged_catalogs_dict: Dict[Tuple[str, str, str], Dict[str, str]] = {}
        for cat in all_catalogs:
            key = (cat.level, cat.semester, cat.combination)
            if key not in merged_catalogs_dict:
                merged_catalogs_dict[key] = {}
            for mod in cat.modules:
                merged_catalogs_dict[key][mod.course_code] = mod.title

        final_catalogs = [
            CourseModuleCatalog(
                level=k[0],
                semester=k[1],
                combination=k[2],
                modules=[CourseModule(course_code=code, title=title) for code, title in modules.items()]
            )
            for k, modules in merged_catalogs_dict.items()
        ]

        # Deduplicate student records by (clean_index, attempt)
        seen_students = set()
        final_students: List[StudentRecord] = []
        for student in all_students:
            s_key = (student.clean_index, student.attempt)
            if s_key not in seen_students:
                seen_students.add(s_key)
                final_students.append(student)

        return FASResultPayload(
            faculty=faculty,
            university=university,
            academic_year=academic_year,
            course_module_tables=final_catalogs,
            results_table=final_students
        )
