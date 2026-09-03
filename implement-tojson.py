import pdfplumber
import json
import re
import pathlib
import argparse

def parse_pdf_to_json(pdf_path, trade_name=None):
    unit_header_pattern = re.compile(r"^UNIT\s*\d+[:\s\-]*(.*)", re.IGNORECASE)
    unit_code_pattern = re.compile(r"Unit\s+[Rr]eference\s*[Nn]umber:?\s*([A-Z0-9/]+)", re.IGNORECASE)
    alt_code_pattern = re.compile(r"(?:Qualification|Level)\s+[Rr]eference\s*[Nn]umber:?\s*([A-Z0-9/]+)", re.IGNORECASE)
    unit_title_pattern = re.compile(r"Unit Title\s*[:-]\s*(.*)", re.IGNORECASE)
    lo_pattern = re.compile(r"(?:Learning\s*Outcome|LO)\.?\s*[:\s]*(\d+)\b", re.IGNORECASE)
    pc_pattern = re.compile(r"^(?:PC\s+)?(\d+\.\d+)$", re.IGNORECASE)
    title_line_pattern = re.compile(r"^TITLE:?\s*(.*)$", re.IGNORECASE)

    # A unit heading can wrap onto the following line ("Unit 001:Safety
    # Standards and Procedures in Network" / "Cabling"). Collecting the
    # remainder stops at the first line that starts one of the unit's
    # detail fields or a repeated table header.
    title_stop_pattern = re.compile(
        r"^(?:UNIT\b|NSQ\b|Credit\s+Value|Guided\s+Learning|Unit\s+Purpose|"
        r"Unit\s+assessment|Assessment\b|LEARNING\b|PERFORMANCE\b|OBJECTIVE\b|"
        r"The\s+learner\b|NATIONAL\s+SKILLS|LEVEL\s*\d)",
        re.IGNORECASE,
    )

    # Sign-off rows closing each unit ("Learner's Signature Date", ...).
    # Anchored at the start of the cell so that performance-criteria text
    # merely mentioning signatures ("...including any required approvals
    # or signatures.") is no longer dropped along with them.
    signoff_row_pattern = re.compile(
        r"^(?:Learner|Candidate|Trainee|Assessor|Trainer|Internal\s+Verifier|"
        r"External\s+Verifier|IQA|EQA)\s*[’'`]?\s*s?\s*Signature\b",
        re.IGNORECASE,
    )

    # Attendee/contributor lists appended after the last unit. The heading
    # wording varies per PDF ("PARTICIPANT FOR ... WORKSHOP", "REVIEW TEAM
    # LIST", "REVALIDATION TEAM LIST", "CRITIQUE TEAM LIST", "VALIDATION
    # TEAM LIST"), so match the shared shape rather than each literal.
    appendix_pattern = re.compile(r"PARTICIPANTS?\s+FOR\b|\bTEAM\s+LIST\b")

    # Wrapped fragments of the repeated table header seen so far, across
    # several different NBTE table layouts. Which *column* these land in
    # varies per page/table, so they're matched by exact text instead.
    HEADER_ROW_FRAGMENTS = {
        "LEARNING", "OBJECTIVE", "(LO)", "THE LEARNER",
        "THE LEARNER WILL:", "THE LEARNER WILL", "WILL:", "WILL",
        "PERFORMANCE", "CRITERIA", "PERFORMANCE CRITERIA",
        "THE LEARNER CAN:", "THE LEARNER CAN",
        "EVIDENCE", "TYPE", "EVIDENCE TYPE",
        "REF.", "REF", "PAGE", "NO.", "NO", "PAGE NO.", "PAGE NO",
        "EVIDENCE REF.", "EVIDENCE REF", "REF. PAGE", "REF. PAGE NO.",
        "EVIDENCE REF. PAGE NO.", "EVIDENCE REF. PAGE",
    }

    data = {
        "trade_name": trade_name,
        "units": []
    }

    current_unit = None
    current_lo = None
    current_pc = None
    last_pc_col_idx = 999
    reached_appendix = False

    def is_plausible_unit_code(code):
        """The Mandatory/Optional summary tables open with a header line
        ("Unit Reference Number NOS Title Credit Guided Remark") that the
        unit-code regex reads as a unit whose code is "NOS", yielding empty
        phantom units. Real reference numbers always carry a digit."""
        return bool(code) and any(ch.isdigit() for ch in code)

    def get_or_create_lo(lo_num, desc=""):
        nonlocal current_lo, current_unit
        if current_unit is None:
            return None
        # Find existing LO with this number
        for lo in current_unit["learning_outcomes"]:
            if lo["lo_num"] == lo_num:
                current_lo = lo
                return lo
        # Create new LO
        current_lo = {
            "lo_num": lo_num,
            "description": desc,
            "performance_criteria": []
        }
        current_unit["learning_outcomes"].append(current_lo)
        return current_lo

    with pdfplumber.open(pdf_path) as pdf:
        # Locate overall trade name
        if not trade_name:
            first_page_text = pdf.pages[0].extract_text()
            if first_page_text:
                lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
                # Prefer the NBTE cover-page "TITLE:" line (name on the same line,
                # or on the next non-blank line if TITLE: stands alone).
                for i, line in enumerate(lines):
                    title_match = title_line_pattern.match(line)
                    if title_match:
                        remainder = title_match.group(1).strip()
                        if remainder:
                            data["trade_name"] = remainder
                        else:
                            for next_line in lines[i + 1:]:
                                if next_line:
                                    data["trade_name"] = next_line
                                    break
                        break
                if not data["trade_name"]:
                    for line in lines:
                        clean_line = re.sub(r"NATIONAL SKILLS QUALIFICATION", "", line, flags=re.IGNORECASE).strip()
                        if clean_line and not clean_line.isdigit():
                            data["trade_name"] = clean_line
                            break
                    if not data["trade_name"] and lines:
                        data["trade_name"] = lines[0]

        for page in pdf.pages:
            text = page.extract_text() or ""

            # Some NBTE PDFs append a workshop/review-attendee list (name/
            # org/address/email/phone) after the last real unit -- the exact
            # heading varies ("PARTICIPANT FOR ... WORKSHOP", "REVIEW TEAM
            # LIST", "REVALIDATION TEAM LIST"). Once we see one, stop
            # extracting entirely for the rest of the document -- otherwise
            # its free-form text gets mistaken for continuation of the last
            # LO/PC.
            if appendix_pattern.search(text.upper()):
                reached_appendix = True
            if reached_appendix:
                continue

            # 1. Process Text for Units
            lines = text.split('\n')
            pending_title = ""
            pending_title_line = False
            pending_code_line = False
            title_wrap_budget = 0
            for line in lines:
                line = line.strip()
                if not line: continue

                # Handle multi-line unit headings (e.g. "Unit 3:" alone, with
                # the actual title "TEAMWORK" on the following line)
                if pending_title_line:
                    pending_title = line
                    pending_title_line = False
                    title_wrap_budget = 2
                    continue

                # Handle multi-line reference numbers (code on next line)
                if pending_code_line:
                    code_match = unit_code_pattern.search(line)
                    if code_match and is_plausible_unit_code(code_match.group(1)):
                        current_unit = {
                            "code": code_match.group(1),
                            "title": pending_title if pending_title else "Unknown Title",
                            "learning_outcomes": []
                        }
                        data["units"].append(current_unit)
                        current_lo = None
                        current_pc = None
                        pending_title = ""
                        pending_code_line = False
                        continue
                    # Could also be a raw code like "CON/PD/009/L2"
                    elif re.match(r'^[A-Z0-9/]+$', line):
                        current_unit = {
                            "code": line.strip(),
                            "title": pending_title if pending_title else "Unknown Title",
                            "learning_outcomes": []
                        }
                        data["units"].append(current_unit)
                        current_lo = None
                        current_pc = None
                        pending_title = ""
                        pending_code_line = False
                        continue
                    pending_code_line = False
                
                header_match = unit_header_pattern.match(line)
                if header_match:
                    pending_title = header_match.group(1).strip()
                    if not pending_title:
                        pending_title_line = True
                    else:
                        title_wrap_budget = 2
                    continue
                
                # Capture separate Unit Title: lines
                title_match = unit_title_pattern.search(line)
                if title_match:
                    pending_title = title_match.group(1).strip()
                    continue
                    
                # Check if this line is just "Unit Reference Number:" with code on next line
                if re.search(r'Unit\s+[Rr]eference\s*[Nn]umber:?\s*$', line, re.IGNORECASE):
                    pending_code_line = True
                    continue
                
                code_match = unit_code_pattern.search(line)
                if code_match and is_plausible_unit_code(code_match.group(1)):
                    code_val = code_match.group(1)
                    current_unit = {
                        "code": code_val,
                        "title": pending_title if pending_title else "Unknown Title",
                        "learning_outcomes": []
                    }
                    data["units"].append(current_unit)
                    current_lo = None
                    current_pc = None
                    pending_title = ""
                    continue
                
                # Alternative reference formats (Qualification/Level) only when a title is pending
                if pending_title:
                    alt_match = alt_code_pattern.search(line)
                    if alt_match:
                        code_val = alt_match.group(1)
                        # Skip level-level codes like CONMS000L2
                        if not re.match(r'^[A-Z]{2,}/?[A-Z]{2,}0+L\d+$', code_val):
                            current_unit = {
                                "code": code_val,
                                "title": pending_title,
                                "learning_outcomes": []
                            }
                            data["units"].append(current_unit)
                            current_lo = None
                            current_pc = None
                            pending_title = ""
                            continue
                
                # Direct code on its own line (rare edge case). Only trust this
                # when a unit title was just seen -- otherwise a code that
                # happens to wrap onto its own line inside the Mandatory Units
                # summary table (no title context at all) gets misread as the
                # start of a new, empty unit.
                if pending_title and re.match(r'^[A-Z]{2,}/[A-Z]{2,}/\d+/L\d+$', line):
                    current_unit = {
                        "code": line.strip(),
                        "title": pending_title if pending_title else "Unknown Title",
                        "learning_outcomes": []
                    }
                    data["units"].append(current_unit)
                    current_lo = None
                    current_pc = None
                    pending_title = ""
                    continue

                # Nothing structural matched. While a unit heading is still
                # pending, such a line is the wrapped remainder of that
                # heading -- without this the title is cut at the page's
                # line break ("...Procedures in Network" losing "Cabling").
                if (pending_title and title_wrap_budget > 0
                        and not line.isdigit()
                        and not title_stop_pattern.match(line)):
                    pending_title = (pending_title + " " + line).strip()
                    title_wrap_budget -= 1

            # 2. Process Tables for LOs and PCs
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            })
            
            for table in tables:
                # pdfplumber sometimes splits one visual table into the real
                # multi-column table plus several spurious single-column
                # "tables" -- word-wrap fragments of repeated headers and
                # already-captured cell text. Those have no LO/PC markers to
                # reset current_lo/current_pc, so their leftover text was
                # bleeding into whatever LO was last active. Real content
                # rows always have more than one populated cell.
                max_cols_used = max(
                    (sum(1 for c in row if c not in (None, "")) for row in table),
                    default=0,
                )
                if max_cols_used <= 1:
                    continue
                # Repeated table headers on continuation pages often get
                # split into several single-cell rows (e.g. "OBJECTIVE",
                # "(LO)", "The learner", "will:") that don't contain the
                # full header phrase, so the row-level header filter below
                # can't catch them. Until a real LO/PC marker shows up in
                # this table, treat every row as still part of that header.
                content_started = False
                for row in table:
                    clean_row = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                    
                    # Skip table headers and footers
                    if any("LEARNING OBJECTIVE" in c.upper() or "PERFORMANCE CRITERIA" in c.upper() for c in clean_row):
                        continue
                    if any("THE LEARNER WILL" in c.upper() or "THE LEARNER CAN" in c.upper() for c in clean_row):
                        continue
                    if any(signoff_row_pattern.match(c) for c in clean_row):
                        continue
                    
                    # Also strip header-like cells from the row
                    for i in range(len(clean_row)):
                        if clean_row[i].upper() in ["EVIDENCE REF", "EVIDENCE TYPE", "PAGE NO", "PAGE NO.", "PAGE NUMBER"]:
                            clean_row[i] = ""
                        elif re.fullmatch(r"Evidence\s+Ref\.?", clean_row[i], re.IGNORECASE):
                            clean_row[i] = ""
                    
                    # Skip empty rows
                    if not any(clean_row):
                        continue

                    if not content_started:
                        has_marker = any(lo_pattern.search(c) for c in clean_row) or \
                                     any(pc_pattern.search(c) for c in clean_row)
                        # A row still counts as header noise only if every
                        # non-blank cell is one of the known wrapped header
                        # fragments -- which column they land in varies by
                        # table layout, so column position isn't reliable.
                        # Any other text (an LO name, a PC code, or bare
                        # continuation text with no marker at all) means real
                        # content has started.
                        is_only_header_fragments = all(
                            (not c) or c.strip().upper() in HEADER_ROW_FRAGMENTS
                            for c in clean_row
                        )
                        if not has_marker and is_only_header_fragments:
                            continue
                        content_started = True

                    # A. Check for LO
                    for c_idx, cell in enumerate(clean_row):
                        lo_match = lo_pattern.search(cell)
                        if lo_match:
                            lo_num = lo_match.group(1)
                            
                            # The description might be the remainder of the cell
                            desc = re.sub(r"(?:Learning\s*Outcome|LO)\.?\s*[:\s]*\d+\b:?", "", cell, flags=re.IGNORECASE).strip()
                            
                            existing = get_or_create_lo(lo_num, desc)
                            if existing and desc and desc not in existing["description"]:
                                existing["description"] = (existing["description"] + " " + desc).strip()
                            current_pc = None
                            last_pc_col_idx = 999  # Reset PC column boundary
                            
                            clean_row[c_idx] = ""
                            
                            # Clear exact duplicates or the standalone "LO X:" in the same row
                            for i in range(len(clean_row)):
                                if re.fullmatch(r"(?:Learning\s*Outcome|LO)\.?\s*[:\s]*" + re.escape(lo_num) + r"\b:?", clean_row[i].strip(), re.IGNORECASE):
                                    clean_row[i] = ""
                                elif clean_row[i].strip() == cell.strip():
                                    clean_row[i] = ""
                            break
                            
                    # C. Check for PC Code
                    for c_idx, cell in enumerate(clean_row):
                        pc_match = pc_pattern.search(cell)
                        if pc_match:
                            pc_code = pc_match.group(1)
                            last_pc_col_idx = c_idx  # Update the boundary
                            
                            # If the PC code prefix doesn't match current LO, switch to the correct LO
                            pc_lo_num = pc_code.split('.')[0]
                            if current_lo is None or current_lo["lo_num"] != pc_lo_num:
                                get_or_create_lo(pc_lo_num)
                            
                            # Clear all cells matching this PC code to avoid duplicating it
                            for i in range(len(clean_row)):
                                if clean_row[i] == cell:
                                    clean_row[i] = ""
                            
                            current_pc = {
                                "pc_code": pc_code,
                                "description": ""
                            }
                            if current_lo is not None:
                                current_lo["performance_criteria"].append(current_pc)
                            break
                            
                    # D. Remaining text goes to description
                    for c_idx, cell in enumerate(clean_row):
                        if not cell:
                            continue
                            
                        # Ignore stray table footers/headers
                        if cell in ["Evidence", "Type", "Ref.", "Page No.", "Evidence Type", "Evidence Ref.", "Page No"]:
                            continue
                            
                        # Decide where this cell belongs based on column index
                        if current_pc is not None:
                            if c_idx < last_pc_col_idx:
                                # Belongs to LO
                                if current_lo is not None:
                                    if cell not in current_lo["description"]:
                                        current_lo["description"] = (current_lo["description"] + " " + cell).strip()
                            else:
                                # Belongs to PC
                                if cell not in current_pc["description"]:
                                    current_pc["description"] = (current_pc["description"] + " " + cell).strip()
                        elif current_lo is not None:
                            # No PC active yet, everything goes to LO
                            if cell not in current_lo["description"]:
                                current_lo["description"] = (current_lo["description"] + " " + cell).strip()

    return clean_data_text(data)


def clean_data_text(obj):
    """Collapse PDF line-wrap hyphenation (e.g. 'Problem-\\nSolving' -> 'Problem- Solving'
    after newline-to-space joining) back into 'Problem-Solving', recursively over all strings."""
    if isinstance(obj, str):
        return re.sub(r'(?<=\w)-\s+(?=\w)', '-', obj).strip()
    if isinstance(obj, list):
        return [clean_data_text(x) for x in obj]
    if isinstance(obj, dict):
        return {k: clean_data_text(v) for k, v in obj.items()}
    return obj


def get_unit_level(code):
    """Extract level from a unit code."""
    m = re.search(r'L(\d+)\s*$', code)
    if m:
        return int(m.group(1))
    return None


def detect_levels(file_data, pdf_stem):
    """Detect all NSQ levels present in the extracted data, grouped by level."""
    levels = {}
    for unit in file_data.get("units", []):
        lvl = get_unit_level(unit.get("code", ""))
        if lvl is None:
            lvl = 2  # fallback
        if lvl not in levels:
            levels[lvl] = []
        levels[lvl].append(unit)
    if not levels:
        m = re.search(r'Level[s]?\s*(\d+)', pdf_stem, re.IGNORECASE)
        lvl = int(m.group(1)) if m else 2
        levels[lvl] = file_data.get("units", [])
    return levels


def process_directory_to_individual_jsons(directory_path, trade_name=None):
    path = pathlib.Path(directory_path)
    base_output = pathlib.Path("extracted_json")

    for pdf_file in path.glob("*.pdf"):
        try:
            print(f"Processing: {pdf_file.name}")
            file_data = parse_pdf_to_json(pdf_file, trade_name)
            levels = detect_levels(file_data, pdf_file.stem)

            for level, units in levels.items():
                level_data = {
                    "trade_name": file_data["trade_name"],
                    "level": level,
                    "units": units
                }
                output_dir = base_output / f"level-{level}"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{pdf_file.stem}.json"
                with open(output_file, 'w', encoding='utf-8') as f:
                    json.dump(level_data, f, indent=2)
                print(f"  Level {level}: {len(units)} units -> {output_file}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract NOS curriculum data from PDFs to individual JSON files.")
    parser.add_argument("--dir", default="./worker", help="Directory containing the PDF files (default: ./worker)")
    parser.add_argument("--trade", help="Optional: Override the trade name for all files. If omitted, it is auto-detected from the PDF.")
    
    args = parser.parse_args()
    process_directory_to_individual_jsons(args.dir, args.trade)
