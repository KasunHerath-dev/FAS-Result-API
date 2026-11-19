"""
File Exporter Module.
Exports structured academic results into Excel-compatible UTF-8-BOM CSV files:
  1. Dynamic Course Module Table (course_modules.csv)
  2. Student Results Wide Table (results_wide.csv - No GPA)
  3. Student Results Long Table (results_long.csv - Relational, No GPA)
"""

import csv
import os
import tempfile
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Union, TextIO
from .schemas import FASResultPayload, CourseModuleCatalog, StudentRecord


class FileExporterException(Exception):
    """Base exception for file export errors."""
    pass


class FileExporter:
    """
    Standardized CSV exporter producing:
      1. Dynamic Course Module Table (Academic Year, Level, Semester, Combination, Course Code, Title)
      2. Student Results Table (Wide & Long layouts, strictly without GPA)
    """

    def __init__(self, output_dir: Union[str, Path] = "exports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    @contextmanager
    def _atomic_csv(self, filename: str, encoding: str) -> Iterator[TextIO]:
        if Path(filename).name != filename or filename in {"", ".."} or "\\" in filename:
            raise FileExporterException("Export filename must be a single filename.")
        target_path = self.output_dir / filename

        temp_path = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", dir=self.output_dir, suffix=".tmp", newline="", encoding=encoding,
                delete=False,
            ) as file:
                temp_path = Path(file.name)
                yield file
            os.replace(temp_path, target_path)
            temp_path = None
        except Exception as exc:
            raise FileExporterException(f"Failed to write {filename}: {exc}") from exc
        finally:
            if temp_path is not None:
                temp_path.unlink(missing_ok=True)

    def export_course_modules(
        self,
        catalogs: List[CourseModuleCatalog],
        filename: str = "course_modules.csv",
        encoding: str = "utf-8-sig",
        *,
        academic_year: str | None = None,
    ) -> Path:
        """
        Exports Table 1 (Course Modules) to CSV.
        Columns: Academic_Year, Level, Semester, Combination, Course_Code, Title
        """
        with self._atomic_csv(filename, encoding) as f:
            writer = csv.writer(f)
            writer.writerow(["Academic_Year", "Level", "Semester", "Combination", "Course_Code", "Title"])
            for cat in catalogs:
                for mod in cat.modules:
                    writer.writerow([
                        cat.academic_year or academic_year,
                        cat.level,
                        cat.semester,
                        cat.combination,
                        mod.course_code,
                        mod.title
                    ])
        return self.output_dir / filename

    def export_results_wide(
        self,
        records: List[StudentRecord],
        filename: str = "results_wide.csv",
        encoding: str = "utf-8-sig",
        *,
        course_codes: Iterable[str] = (),
        academic_year: str | None = None,
    ) -> Path:
        """
        Pivots student results into dynamic course columns.
        Include catalog codes supplied in course_codes even when they have no grades.
        Columns: Index, Base_Index, Combination, Academic_Year, Level, Semester, Exam_Type,
        Student_Type, Attempt, [Courses...], Remarks
        Strictly NO GPA.
        """
        all_courses = sorted(set(course_codes).union(
            res.course_code for rec in records for res in rec.results
        ))
        headers = [
            "Index", "Base_Index", "Combination", "Academic_Year", "Level", "Semester",
            "Exam_Type", "Student_Type", "Attempt", *all_courses, "Remarks"
        ]

        with self._atomic_csv(filename, encoding) as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for rec in records:
                grade_map = {
                    res.course_code: res.grade.strip()
                    for res in rec.results if res.grade.strip() != "-"
                }
                course_grades = [grade_map.get(code, "") for code in all_courses]
                writer.writerow([
                    rec.raw_index or rec.clean_index,
                    rec.clean_index if rec.clean_index.isdecimal() else "",
                    rec.combination,
                    rec.academic_year or academic_year,
                    rec.level,
                    rec.semester,
                    rec.exam_type,
                    rec.student_type,
                    rec.attempt,
                    *course_grades,
                    rec.remarks or ""
                ])
        return self.output_dir / filename

    def export_results_long(
        self,
        records: List[StudentRecord],
        filename: str = "results_long.csv",
        encoding: str = "utf-8-sig",
        *,
        academic_year: str | None = None,
    ) -> Path:
        """
        Exports student results in normalized relational rows.
        Excludes un-enrolled course hyphens.
        """
        headers = [
            "Index", "Base_Index", "Combination", "Academic_Year", "Level", "Semester",
            "Exam_Type", "Student_Type", "Attempt", "Course_Code", "Grade"
        ]

        with self._atomic_csv(filename, encoding) as f:
            writer = csv.writer(f)
            writer.writerow(headers)
            for rec in records:
                for res in rec.results:
                    grade = res.grade.strip()
                    if grade in {"", "-", "UNREAD"}:
                        continue
                    writer.writerow([
                        rec.raw_index or rec.clean_index,
                        rec.clean_index if rec.clean_index.isdecimal() else "",
                        rec.combination,
                        rec.academic_year or academic_year,
                        rec.level,
                        rec.semester,
                        rec.exam_type,
                        rec.student_type,
                        rec.attempt,
                        res.course_code,
                        grade
                    ])
        return self.output_dir / filename

    def export_all(
        self,
        payload: FASResultPayload,
        base_name: str = "fas_results"
    ) -> Dict[str, Path]:
        """Convenience method generating both Table 1 and Table 2 (Wide & Long)."""
        return {
            "course_modules": self.export_course_modules(
                payload.course_module_tables,
                f"{base_name}_modules.csv",
                academic_year=payload.academic_year,
            ),
            "results_wide": self.export_results_wide(
                payload.results_table,
                f"{base_name}_results_wide.csv",
                course_codes=(
                    module.course_code
                    for catalog in payload.course_module_tables
                    for module in catalog.modules
                ),
                academic_year=payload.academic_year,
            ),
            "results_long": self.export_results_long(
                payload.results_table,
                f"{base_name}_results_long.csv",
                academic_year=payload.academic_year,
            )
        }
