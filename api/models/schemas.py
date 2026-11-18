"""
Pydantic Schemas for FAS Result API.
Defines data structures for:
  1. Dynamic Course Module Catalogs (Course Code, Title, Level, Semester, Combination)
  2. Student Result Records (Regular, Repeat, Medical without GPA)
"""

from typing import List, Optional, Literal, Tuple
from pydantic import BaseModel, Field
import re


def parse_student_index(raw_index: str, is_repeat_section: bool = False) -> Tuple[str, Literal["Regular", "Repeat", "Medical"], int, bool]:
    """
    Parses a raw index/registration string into its normalized components:
      - clean_index: Base registration number (e.g. '222002', '172149')
      - student_type: 'Regular', 'Repeat', or 'Medical'
      - attempt: Sitting attempt number (1 for regular/medical, count('R') + 1 for repeat)
      - is_medical: True if suffix contains 'M' or 'M.'
    
    Examples:
      '232004'        -> ('232004', 'Regular', 1, False)
      '222002R'       -> ('222002', 'Repeat', 2, False)
      '172149RRRRRR'  -> ('172149', 'Repeat', 7, False)
      '222039M.'      -> ('222039', 'Medical', 1, True)
      '222045M'       -> ('222045', 'Medical', 1, True)
    """
    raw = raw_index.strip()
    
    # Check for medical excuse suffix: M or M.
    med_match = re.search(r"^(\d+)[mM]\.?$", raw)
    if med_match:
        base_id = med_match.group(1)
        return (base_id, "Medical", 1, True)
        
    # Check for repeat suffix: one or more 'R's
    rep_match = re.search(r"^(\d+)([rR]+)$", raw)
    if rep_match:
        base_id = rep_match.group(1)
        r_count = len(rep_match.group(2))
        return (base_id, "Repeat", r_count + 1, False)
        
    # If in repeat section but has no suffix (e.g. earlier batch student)
    if is_repeat_section:
        clean = re.sub(r"[^\d]", "", raw)
        return (clean or raw, "Repeat", 2, False)
        
    clean = re.sub(r"[^\w]", "", raw)
    return (clean, "Regular", 1, False)


# ========================================================
# TABLE 1: DYNAMIC COURSE MODULE SCHEMA
# ========================================================
class CourseModule(BaseModel):
    course_code: str = Field(description="Course unit code, e.g. 'CMIS2214', 'MATH2213', 'ELPC 2220'")
    title: str = Field(description="Descriptive title of the course unit, e.g. 'Data Structures & Analysis of Algorithms'")


class CourseModuleCatalog(BaseModel):
    level: str = Field(description="Academic Level, e.g. 'Level 2'")
    semester: str = Field(description="Semester designation, e.g. 'Semester II'")
    combination: str = Field(description="Combination identifier, e.g. 'Combination I', 'Combination III', or 'All (Repeat)'")
    modules: List[CourseModule] = Field(
        default_factory=list,
        description="List of course modules offered for this specific combination, level, and semester"
    )


# ========================================================
# TABLE 2: STUDENT RESULTS SCHEMA (STRICTLY NO GPA)
# ========================================================
class CourseGrade(BaseModel):
    course_code: str = Field(description="Course unit code matching the module catalog, e.g. 'CMIS2214'")
    grade: str = Field(description="Obtained grade symbol: A+, A, A-, B+, B, B-, C+, C, C-, D+, D, E, I, P")


class StudentRecord(BaseModel):
    raw_index: str = Field(description="Verbatim index/registration number from the sheet, e.g. '222002R', '172149RRRRRR', '222039M.'")
    clean_index: str = Field(description="Base student index number without repeat/medical suffixes, e.g. '222002', '172149'")
    combination: str = Field(description="Combination name or number, e.g. 'Combination I', 'Combination III', or '1', '3'")
    level: str = Field(default="Level 2", description="Academic level, e.g. 'Level 2'")
    semester: str = Field(default="Semester II", description="Semester, e.g. 'Semester II'")
    exam_type: Literal["Regular", "Repeat"] = Field(default="Regular", description="Regular vs. Repeat examination session")
    student_type: Literal["Regular", "Repeat", "Medical"] = Field(
        default="Regular",
        description="Classified student sitting type: Regular, Repeat (suffix 'R'), or Medical (suffix 'M')"
    )
    attempt: int = Field(
        default=1,
        description="Examination sitting attempt count (1 for regular/medical, count('R') + 1 for repeat)"
    )
    results: List[CourseGrade] = Field(
        default_factory=list,
        description="List of active course grades obtained. Excludes un-enrolled courses marked with hyphens ('-')"
    )
    remarks: Optional[str] = Field(default=None, description="Official remarks or academic status notes")


# ========================================================
# UNIFIED PAYLOAD
# ========================================================
class FASResultPayload(BaseModel):
    faculty: str = Field(default="Faculty of Applied Sciences", description="Faculty name")
    university: str = Field(default="Wayamba University of Sri Lanka", description="University name")
    academic_year: Optional[str] = Field(default="2023/2024", description="Academic Year")
    course_module_tables: List[CourseModuleCatalog] = Field(
        default_factory=list,
        description="Dynamic Course Module Catalogs partitioned by Level, Semester, and Combination"
    )
    results_table: List[StudentRecord] = Field(
        default_factory=list,
        description="Complete list of all regular and repeat student result records"
    )
