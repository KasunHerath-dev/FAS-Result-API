"""
File Exporter Module.
Exports structured academic results into Excel-compatible UTF-8-BOM CSV files:
  1. Dynamic Course Module Table (course_modules.csv)
  2. Student Results Wide Table (results_wide.csv - No GPA)
  3. Student Results Long Table (results_long.csv - Relational, No GPA)
"""

import csv
import os
from pathlib import Path
from typing import List, Dict, Union, Literal
from .schemas import FASResultPayload, CourseModuleCatalog, StudentRecord


class FileExporterException(Exception):
    """Base exception for file export errors."""
    pass


class FileExporter:
    """
    Standardized CSV exporter producing:
      1. Dynamic Course Module Table (Level, Semester, Combination, Course Code, Title)
      2. Student Results Table (Wide & Long layouts, strictly without GPA)
    """

    def __init__(self, output_dir: Union[str, Path] = "exports"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def export_course_modules(
        self,
        catalogs: List[CourseModuleCatalog],
        filename: str = "course_modules.csv",
        encoding: str = "utf-8-sig"
    ) -> Path:
        """
        Exports Table 1 (Course Modules) to CSV.
        Columns: Level, Semester, Combination, Course_Code, Title
        """
        target_path = self.output_dir / filename
        temp_path = target_path.with_suffix(".tmp")

        try:
            with open(temp_path, "w", newline="", encoding=encoding) as f:
                writer = csv.writer(f)
                writer.writerow(["Level", "Semester", "Combination", "Course_Code", "Title"])
                for cat in catalogs:
                    for mod in cat.modules:
                        writer.writerow([
                            cat.level,
                            cat.semester,
                            cat.combination,
                            mod.course_code,
                            mod.title
                        ])
            os.replace(temp_path, target_path)
            return target_path
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise FileExporterException(f"Failed to export course modules: {e}") from e

    def export_results_wide(
        self,
        records: List[StudentRecord],
        filename: str = "results_wide.csv",
        encoding: str = "utf-8-sig"
    ) -> Path:
        """
        Pivots student results into dynamic course columns.
        Columns: Index, Raw_Index, Combination, Level, Semester, Exam_Type, Student_Type, Attempt, [Courses...], Remarks
        Strictly NO GPA.
        """
        target_path = self.output_dir / filename
        temp_path = target_path.with_suffix(".tmp")

        try:
            # Collect unique course codes across records
            all_courses = sorted(list({res.course_code for rec in records for res in rec.results}))
            headers = [
                "Index", "Raw_Index", "Combination", "Level", "Semester",
                "Exam_Type", "Student_Type", "Attempt", *all_courses, "Remarks"
            ]

            with open(temp_path, "w", newline="", encoding=encoding) as f:
                writer = csv.writer(f)
                writer.writerow(headers)

                for rec in records:
                    grade_map = {res.course_code: res.grade for res in rec.results}
                    course_grades = [grade_map.get(c, "-") for c in all_courses]
                    row = [
                        rec.clean_index,
                        rec.raw_index,
                        rec.combination,
                        rec.level,
                        rec.semester,
                        rec.exam_type,
                        rec.student_type,
                        rec.attempt,
                        *course_grades,
                        rec.remarks or ""
                    ]
                    writer.writerow(row)

            os.replace(temp_path, target_path)
            return target_path
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise FileExporterException(f"Failed to export wide results: {e}") from e

    def export_results_long(
        self,
        records: List[StudentRecord],
        filename: str = "results_long.csv",
        encoding: str = "utf-8-sig"
    ) -> Path:
        """
        Exports student results in normalized relational rows.
        Excludes un-enrolled course hyphens.
        """
        target_path = self.output_dir / filename
        temp_path = target_path.with_suffix(".tmp")

        try:
            headers = [
                "Index", "Raw_Index", "Combination", "Level", "Semester",
                "Exam_Type", "Student_Type", "Attempt", "Course_Code", "Grade"
            ]

            with open(temp_path, "w", newline="", encoding=encoding) as f:
                writer = csv.writer(f)
                writer.writerow(headers)

                for rec in records:
                    for res in rec.results:
                        writer.writerow([
                            rec.clean_index,
                            rec.raw_index,
                            rec.combination,
                            rec.level,
                            rec.semester,
                            rec.exam_type,
                            rec.student_type,
                            rec.attempt,
                            res.course_code,
                            res.grade
                        ])

            os.replace(temp_path, target_path)
            return target_path
        except Exception as e:
            if temp_path.exists():
                temp_path.unlink()
            raise FileExporterException(f"Failed to export long results: {e}") from e

    def export_all(
        self,
        payload: FASResultPayload,
        base_name: str = "fas_results"
    ) -> Dict[str, Path]:
        """Convenience method generating both Table 1 and Table 2 (Wide & Long)."""
        return {
            "course_modules": self.export_course_modules(
                payload.course_module_tables,
                f"{base_name}_modules.csv"
            ),
            "results_wide": self.export_results_wide(
                payload.results_table,
                f"{base_name}_results_wide.csv"
            ),
            "results_long": self.export_results_long(
                payload.results_table,
                f"{base_name}_results_long.csv"
            )
        }
