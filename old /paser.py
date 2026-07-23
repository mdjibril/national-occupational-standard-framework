import pdfplumber
import json
import pathlib
import re
import argparse


# ==========================================================
# CONFIG
# ==========================================================

TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 3,
    "join_tolerance": 3,
    "intersection_tolerance": 3,
}

LO_PATTERN = re.compile(
    r'LO\s*:?\s*(\d+)\s*(.*)',
    re.IGNORECASE
)

PC_PATTERN = re.compile(
    r'^(\d+\.\d+)\s*(.*)$'
)

UNIT_HEADER_PATTERN = re.compile(
    r'Unit\s+\d+\s*[:\-]?\s*(.*)',
    re.IGNORECASE
)

UNIT_CODE_PATTERN = re.compile(
    r'([A-Z]{2,}/[A-Z]{2,}/L\d+/\d+)',
    re.IGNORECASE
)


# ==========================================================
# HELPERS
# ==========================================================

def clean_text(text):

    if text is None:
        return ""

    text = str(text)

    text = text.replace("\n", " ")
    text = text.replace("\r", " ")

    text = re.sub(r'\s+', ' ', text)

    return text.strip()


def is_header_row(row_text):

    row_text = row_text.upper()

    headers = [
        "LEARNING OBJECTIVE",
        "PERFORMANCE CRITERIA",
        "EVIDENCE TYPE",
        "EVIDENCE REF",
        "PAGE NO",
        "THE LEARNER WILL",
        "THE LEARNER CAN"
    ]

    return any(h in row_text for h in headers)


def parse_lo_cell(lo_text):

    lo_text = clean_text(lo_text)

    match = LO_PATTERN.search(lo_text)

    if not match:
        return None

    lo_num = match.group(1)

    description = match.group(2).strip()

    description = re.sub(
        r'^[:\-\s]+',
        '',
        description
    )

    return lo_num, description


# ==========================================================
# UNIT TITLE EXTRACTION
# ==========================================================

def extract_unit_title(page_text):

    for line in page_text.splitlines():

        line = line.strip()

        match = UNIT_HEADER_PATTERN.search(line)

        if match:
            return clean_text(match.group(1))

    return ""


def extract_unit_code(page_text):

    match = UNIT_CODE_PATTERN.search(page_text)

    if match:
        return match.group(1)

    return ""


# ==========================================================
# TABLE PARSER
# ==========================================================

def parse_tables(pdf):

    unit = {
        "code": "",
        "title": "",
        "learning_outcomes": []
    }

    lo_lookup = {}

    current_lo = None
    current_pc = None

    current_lo_text = ""

    for page in pdf.pages:

        page_text = page.extract_text() or ""

        if not unit["title"]:
            unit["title"] = extract_unit_title(page_text)

        if not unit["code"]:
            unit["code"] = extract_unit_code(page_text)

        tables = page.extract_tables(TABLE_SETTINGS)

        if not tables:
            continue

        for table in tables:

            for row in table:

                row = [
                    clean_text(cell)
                    for cell in row
                ]

                row_text = " ".join(row)

                if not row_text.strip():
                    continue

                if is_header_row(row_text):
                    continue

                # ==================================================
                # COLUMN ASSUMPTION
                #
                # COL0 = LO CELL
                # COL1 = PC CODE
                # COL2 = PC DESCRIPTION
                # Remaining columns ignored
                # ==================================================

                lo_cell = row[0] if len(row) > 0 else ""
                pc_code_cell = row[1] if len(row) > 1 else ""
                pc_desc_cell = row[2] if len(row) > 2 else ""

                # ==========================================
                # MERGED CELL RECONSTRUCTION
                # ==========================================

                if lo_cell:
                    current_lo_text = lo_cell

                lo_info = parse_lo_cell(current_lo_text)

                if lo_info:

                    lo_num, lo_desc = lo_info

                    if lo_num not in lo_lookup:

                        current_lo = {
                            "lo_num": lo_num,
                            "description": lo_desc,
                            "performance_criteria": []
                        }

                        unit["learning_outcomes"].append(
                            current_lo
                        )

                        lo_lookup[lo_num] = current_lo

                    else:

                        current_lo = lo_lookup[lo_num]

                        if (
                            not current_lo["description"]
                            and lo_desc
                        ):
                            current_lo["description"] = lo_desc

                # ==========================================
                # PC ROW
                # ==========================================

                if pc_code_cell:

                    pc_match = PC_PATTERN.match(
                        pc_code_cell
                    )

                    if pc_match and current_lo:

                        pc_code = pc_match.group(1)

                        current_pc = {
                            "pc_code": pc_code,
                            "description": pc_desc_cell
                        }

                        current_lo[
                            "performance_criteria"
                        ].append(current_pc)

                        continue

                # ==========================================
                # CONTINUATION ROW
                # ==========================================

                if (
                    current_pc
                    and not pc_code_cell
                    and pc_desc_cell
                ):

                    current_pc["description"] += (
                        " " + pc_desc_cell
                    )

                    current_pc["description"] = clean_text(
                        current_pc["description"]
                    )

    return unit


# ==========================================================
# VALIDATION
# ==========================================================

def validate_unit(unit):

    errors = []

    for lo in unit["learning_outcomes"]:

        lo_num = lo["lo_num"]

        for pc in lo["performance_criteria"]:

            pc_prefix = pc["pc_code"].split(".")[0]

            if pc_prefix != lo_num:

                errors.append(
                    f"PC {pc['pc_code']} "
                    f"found under LO {lo_num}"
                )

    return errors


# ==========================================================
# MAIN PDF PARSER
# ==========================================================

def parse_pdf(pdf_path):

    with pdfplumber.open(pdf_path) as pdf:

        unit = parse_tables(pdf)

        validation_errors = validate_unit(unit)

        if validation_errors:

            print("\nVALIDATION WARNINGS")

            for err in validation_errors:
                print(" -", err)

        return unit


# ==========================================================
# DIRECTORY PROCESSOR
# ==========================================================

def process_directory(directory):

    directory = pathlib.Path(directory)

    output_dir = directory / "json_output"

    output_dir.mkdir(exist_ok=True)

    all_units = []

    for pdf_file in directory.glob("*.pdf"):

        try:

            print(
                f"Processing {pdf_file.name}"
            )

            unit = parse_pdf(pdf_file)

            all_units.append(unit)

            outfile = (
                output_dir /
                f"{pdf_file.stem}.json"
            )

            with open(
                outfile,
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    unit,
                    f,
                    indent=2,
                    ensure_ascii=False
                )

            print(
                f"Saved -> {outfile}"
            )

        except Exception as e:

            print(
                f"Failed {pdf_file.name}"
            )

            print(e)

    master_file = (
        output_dir /
        "all_units.json"
    )

    with open(
        master_file,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            {
                "units": all_units
            },
            f,
            indent=2,
            ensure_ascii=False
        )

    print(
        f"\nMaster JSON saved -> "
        f"{master_file}"
    )


# ==========================================================
# ENTRY
# ==========================================================

if __name__ == "__main__":

    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--dir",
        required=True,
        help="Folder containing PDFs"
    )

    args = parser.parse_args()

    process_directory(args.dir)