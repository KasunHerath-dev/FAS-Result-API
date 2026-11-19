"""Read a ruled results table at cell coordinates before interpreting its text."""

import math
import re
from itertools import groupby, pairwise
from statistics import median

from PIL import Image, ImageOps
from pydantic import BaseModel
import pytesseract


GRADES = {
    "A+", "A", "A-", "B+", "B", "B-", "C+", "C", "C-", "D+", "D", "E",
    "I", "P", "AB", "MC", "WH", "NE", "F",
}
GRADE_CHARACTERS = "ABCDEIFPMWHN+-"
INDEX_PATTERN = re.compile(r"\d{5,7}(?:R+(?:/M\.?)?|M\.?)?")


class GridRow(BaseModel):
    serial: str
    index: str
    combination: str = ""
    grades: list[str]


class GridPage(BaseModel):
    heading: str
    repeat: bool
    courses: list[tuple[str, str]]
    rows: list[GridRow]
    warnings: list[str]


def _line_centers(mask: list[bool]) -> list[int]:
    centers = []
    for present, group in groupby(enumerate(mask), key=lambda pair: pair[1]):
        if present:
            points = [point for point, _ in group]
            centers.append(round((points[0] + points[-1]) / 2))
    return centers


def _project(image: Image.Image, size: tuple[int, int]) -> list[int]:
    return list(image.resize(size, Image.Resampling.BOX).get_flattened_data())


def _grid(image: Image.Image) -> tuple[Image.Image, list[int], list[int]] | None:
    # Measure on a small image and crop the original pixels for recognition.
    width = min(image.width, 1754)
    height = round(image.height * width / image.width)
    preview = image.resize((width, height))

    def horizontal(sheet: Image.Image, left: float, right: float) -> list[int]:
        strip = sheet.crop((int(width * left), 0, int(width * right), height))
        return _line_centers([value < 115 for value in _project(strip, (1, height))])

    left = horizontal(preview, .26, .45)
    right = horizontal(preview, .55, .74)
    offsets = [b - a for a in left for b in right if abs(a - b) <= 14]
    if not offsets:
        return None

    angle = math.degrees(math.atan(median(offsets) / (width * .29)))
    preview = preview.rotate(angle, fillcolor=255)
    ys = horizontal(preview, .29, .72)
    if len(ys) < 4:
        return None

    # A short code header and a tall title header precede the evenly spaced rows.
    pitch = median(b - a for a, b in pairwise(ys))
    if not (1.8 * pitch < ys[2] - ys[1] < 7 * pitch):
        return None
    if any(not .65 * pitch < b - a < 1.4 * pitch for a, b in pairwise(ys[2:])):
        return None

    data = _project(preview.crop((0, ys[2] + 2, width, ys[-1] - 2)), (width, 1))
    titles = _project(preview.crop((0, ys[1] + 2, width, ys[2] - 2)), (width, 1))
    xs = _line_centers([
        value < 165 and min(data[max(0, x - 2):x + 3]) < 126
        for x, value in enumerate(titles)
    ])
    if len(xs) < 5 or xs[-1] - xs[0] < width * .5:
        return None
    if min(b - a for a, b in pairwise(xs)) < width * .018:
        return None

    return (
        image.rotate(angle, fillcolor=255),
        [round(x * image.width / width) for x in xs],
        [round(y * image.height / height) for y in ys],
    )


def _ink(image: Image.Image) -> Image.Image | None:
    bounds = ImageOps.invert(image).point(lambda value: 255 if value > 140 else 0).getbbox()
    return image.crop(bounds) if bounds else None


def _read_cells(
    cells: list[list[Image.Image | None]], alphabet: str, size: tuple[int, int],
) -> list[list[str]]:
    """OCR a whitespace-padded composite and map words back by their coordinates."""
    width, height = size
    canvas = Image.new("L", (len(cells[0]) * width, len(cells) * height), 255)
    for ri, row in enumerate(cells):
        for ci, glyph in enumerate(row):
            if glyph is None:
                continue
            if glyph.width > width - 12 or glyph.height > height - 12:
                glyph = glyph.copy()
                glyph.thumbnail((width - 12, height - 12))
            canvas.paste(glyph, (
                ci * width + (width - glyph.width) // 2,
                ri * height + (height - glyph.height) // 2,
            ))

    words = pytesseract.image_to_data(
        canvas, lang="eng", output_type=pytesseract.Output.DICT,
        config=f"--psm 6 -c 'tessedit_char_whitelist={alphabet} '",
    )
    values = [["" for _ in row] for row in cells]
    for text, x, y, w, h in zip(*(words[key] for key in ("text", "left", "top", "width", "height"))):
        if text.strip():
            values[(y + h // 2) // height][(x + w // 2) // width] += re.sub(r"\s+", "", text)
    return values


def _read_excerpt(image: Image.Image, psm: int = 6, alphabet: str = "") -> str:
    config = f"--psm {psm}"
    if alphabet:
        config += f" -c 'tessedit_char_whitelist={alphabet} '"
    return pytesseract.image_to_string(
        ImageOps.expand(image, border=12, fill=255), lang="eng", config=config,
    ).strip()


def _grade(text: str) -> str:
    return text.translate(str.maketrans({"1": "I", "l": "I", "|": "I"})).strip()


def read_results_grid(image: Image.Image) -> GridPage | None:
    grid = _grid(image)
    if grid is None:
        return None
    sheet, xs, ys = grid
    margin = max(3, round(sheet.width / 450))
    heading = _read_excerpt(sheet.crop((xs[0], 0, xs[-1], ys[0] - margin)))
    registration_header = _read_excerpt(sheet.crop((
        xs[0] + margin, ys[1] + margin, xs[3] - margin, ys[2] - margin,
    )))
    if "Repeat" not in heading and not re.search(r"Index|Serial|Ser\b|Registration", registration_header, re.I):
        return None
    repeat = bool(re.search(r"\bRepeat\b", heading, re.I)) or "COMB" in registration_header
    metadata_columns = 3 if repeat else 2

    courses = []
    warnings = []
    for number, (left, right) in enumerate(pairwise(xs[metadata_columns:]), 1):
        code_image = sheet.crop((left + margin, ys[0] + margin, right - margin, ys[1] - margin))
        code = re.sub(r"\s+", "", _read_excerpt(code_image, 7, "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"))
        title_lines = _read_excerpt(sheet.crop((
            left + margin, ys[1] + margin, right - margin, ys[2] - margin,
        ))).splitlines()
        title = " ".join(" ".join(title_lines).split())
        title = re.sub(r" (?:\||1)$", " I", title)
        title = re.sub(r" Il$", " II", title)
        title = title.replace("Semiconduc tor", "Semiconductor").replace("Managemen t", "Management")
        # The printed English proficiency title disambiguates the narrow 1/2 in its code.
        if code.startswith("ELPC") and re.search(r"\bCourse I[1I]?\b", title):
            code = "ELPC2220" if re.search(r"\bCourse I[1I]\b", title) else "ELPC2120"
        if not re.fullmatch(r"[A-Z]{3,4}\d{4}", code) or code in {key for key, _ in courses}:
            warnings.append(f"Uncertain course code in column {number}")
            code = f"UNREAD_COURSE_{number}"
        courses.append((code, title or code))

    meta_cells = []
    grade_cells = []
    for top, bottom in pairwise(ys[2:]):
        row_metadata = []
        row_grades = []
        for ci, (left, right) in enumerate(pairwise(xs)):
            if ci < metadata_columns:
                row_metadata.append(_ink(sheet.crop((
                    left + margin, top + margin, right - margin, bottom - margin,
                ))))
            else:
                center = (left + right) // 2
                half_width = min((right - left) // 2 - margin, round(sheet.width / 55))
                glyph = _ink(sheet.crop((
                    center - half_width, top + margin * 2,
                    center + half_width, bottom - margin * 2,
                )))
                row_grades.append(glyph)
        meta_cells.append(row_metadata)
        grade_cells.append(row_grades)

    meta = list(zip(*[
        [row[0] for row in _read_cells([[glyph] for glyph in column], alphabet, (330, 70))]
        for column, alphabet in zip(zip(*meta_cells), ["0123456789"] * (metadata_columns - 1) + ["0123456789RM./"])
    ]))
    visible = [
        [glyph if glyph is not None and glyph.height > max(3, round(sheet.width / 390)) else None for glyph in row]
        for row in grade_cells
    ]
    primary = _read_cells(visible, GRADE_CHARACTERS, (160, 63))
    reversed_cells = [row[::-1] for row in visible[::-1]]
    secondary = [row[::-1] for row in _read_cells(reversed_cells, GRADE_CHARACTERS, (190, 75))[::-1]]

    rows = []
    for ri, (fields, first, second, glyphs) in enumerate(zip(meta, primary, secondary, visible)):
        *combination, serial, index = fields
        if not INDEX_PATTERN.fullmatch(index):
            glyph = meta_cells[ri][-1]
            index = re.sub(r"\s+", "", _read_excerpt(glyph, 7, "0123456789RM./")) if glyph else ""
        if not INDEX_PATTERN.fullmatch(index):
            warnings.append(f"Row {ri + 1} (serial {serial or '?'}) has an unreadable registration number")
        grades = []
        for ci, (a, b, glyph) in enumerate(zip(first, second, glyphs)):
            grade = ""
            if glyph is not None:
                a, b = _grade(a), _grade(b)
                if glyph.height > glyph.width * 2 and not ({a, b} & {"A", "B", "C", "D", "E", "P"}):
                    grade = "I"
                elif a == b and a in GRADES:
                    grade = a
                else:
                    retry = _grade(_read_excerpt(glyph, 7, GRADE_CHARACTERS + "1l|"))
                    if retry in GRADES:
                        grade = retry
                    elif a in GRADES or b in GRADES:
                        grade = a if a in GRADES else b
                    if not grade or len({value for value in (a, b, retry) if value in GRADES}) > 1:
                        warnings.append(
                            f"Serial {serial or '?'}, {courses[ci][0]}: review grade "
                            f"({a or '?'}/{b or '?'}/{retry or '?'}) in table row {ri + 1}."
                        )
                    if not grade:
                        grade = "UNREAD"
            grades.append(grade)
        rows.append(GridRow(serial=serial, index=index, combination="".join(combination), grades=grades))

    return GridPage(heading=heading, repeat=repeat, courses=courses, rows=rows, warnings=warnings)
