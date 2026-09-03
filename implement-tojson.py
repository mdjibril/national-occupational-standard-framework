import pdfplumber
import json
import re
import pathlib
import argparse

def parse_pdf_to_json(pdf_path, trade_name=None):
    unit_header_pattern = re.compile(r"UNIT\s*\d+[:\s\-]*(.*)", re.IGNORECASE)
    # Some pages render the heading as a bare "005: Title" with the "UNIT"
    # word left orphaned on a separate line (or a separate page entirely,
    # across an intervening signature block) -- 2-3 digits is enough to
    # avoid the numbered "1. Direct Observation (DO)" assessment-method
    # lists, which use a single digit and a period, never a colon.
    bare_unit_header_pattern = re.compile(r"^(\d{2,3}):\s+(.+)$")
    unit_code_pattern = re.compile(r"(?:Unit\s+)?[Rr]eference\s*[Nn]umber:?\s*([A-Z0-9/]+)", re.IGNORECASE)
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
        r"The\s+learner\b|NATIONAL\s+SKILLS|LEVEL\s*\d|Validated\b)",
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
        "LEARNING", "OBJECTIVE", "(LO)", "OBJECTIVE (LO)", "THE LEARNER",
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
    # A unit's title and reference number don't always land on the same
    # page (the title can be the last line of one page, with "Unit
    # reference number: ..." opening the next) -- these must persist across
    # the page boundary like current_unit/current_lo/current_pc already do,
    # not reset per page.
    pending_title = ""
    pending_title_line = False
    pending_code_line = False
    title_wrap_budget = 0

    def is_plausible_unit_code(code):
        """The Mandatory/Optional summary tables open with a header line
        ("Unit Reference Number NOS Title Credit Guided Remark") that the
        unit-code regex reads as a unit whose code is "NOS", yielding empty
        phantom units. Real reference numbers always carry a digit."""
        return bool(code) and any(ch.isdigit() for ch in code)

    def is_repeat_of_current_title(candidate):
        """Every unit's heading gets rendered a second time immediately
        before its own LO/PC table, right after the "Unit Purpose"/
        assessment-methods prose that already consumed the first render's
        pending_title. Re-arming pending_title (and its wrap-continuation
        budget) for this repeat is pure risk: with nothing left to consume
        it, the next couple of unrelated lines it happens to land on --
        real PC/LO text, or eventually a stray reference-number-shaped cell
        in a much later level's summary table -- can silently get glued
        onto it or misread as a whole new unit."""
        return (
            current_unit is not None
            and candidate.strip().rstrip('.').casefold()
            == current_unit["title"].strip().rstrip('.').casefold()
        )

    def create_unit(code, title):
        nonlocal current_unit, current_lo, current_pc, last_creation_line_idx, unit_before_last_creation
        unit_before_last_creation = current_unit
        last_creation_line_idx = line_idx
        current_unit = {
            "code": code,
            "title": title if title else "Unknown Title",
            "learning_outcomes": []
        }
        data["units"].append(current_unit)
        current_lo = None
        current_pc = None

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

            # Some pages end with the *next* unit's full heading and
            # reference number rendered as a "coming up" preview, after that
            # page's own table content -- e.g. a page holding unit 003's
            # whole LO/PC table closes with "UNIT 004: ... / Unit reference
            # number: CON/ACI/004/L2" as its last two lines, with unit 004's
            # own content only starting next page. Other pages instead
            # *open* with a brand new unit's heading and reference number,
            # immediately followed on that same page by that same unit's own
            # LO/PC table. Since the text loop below runs to completion
            # (and so creates whichever unit(s) it encounters) before the
            # table loop for this same page runs, naively using current_unit
            # for tables gets the trailing-preview case wrong (attributing
            # unit 003's table to freshly-created unit 004), while naively
            # using the unit from before this page started gets the other
            # case wrong (attributing unit 005's own table on its own
            # opening page back to unit 004). Distinguish them by checking
            # whether anything table-shaped (a PC code, an LO marker, or the
            # table's own header row) follows the *last* unit created on
            # this page: if nothing does, that creation was just a trailing
            # preview and this page's tables belong to the unit active
            # before it; otherwise they belong to the newly created unit.
            last_creation_line_idx = None
            unit_before_last_creation = None

            # 1. Process Text for Units
            lines = text.split('\n')
            for line_idx, line in enumerate(lines):
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
                        create_unit(code_match.group(1), pending_title)
                        pending_title = ""
                        pending_code_line = False
                        continue
                    # Could also be a raw code like "CON/PD/009/L2", possibly
                    # followed on the same line by more fields that got
                    # merged in ("CON/ACI/005/L3 NSQ level: 3") -- take just
                    # the leading code-shaped token.
                    elif re.match(r'^([A-Z0-9/]+)\b', line) and is_plausible_unit_code(re.match(r'^([A-Z0-9/]+)\b', line).group(1)):
                        create_unit(re.match(r'^([A-Z0-9/]+)\b', line).group(1), pending_title)
                        pending_title = ""
                        pending_code_line = False
                        continue
                    pending_code_line = False
                
                # search(), not match(): a unit heading can be glued onto the
                # end of the preceding Key/glossary line ("...INSTALLATION
                # UNIT 001: Health, Safety and Environment") instead of
                # starting the line.
                header_match = unit_header_pattern.search(line)
                if header_match:
                    candidate_title = header_match.group(1).strip()
                    if not is_repeat_of_current_title(candidate_title):
                        pending_title = candidate_title
                        if not pending_title:
                            pending_title_line = True
                        else:
                            title_wrap_budget = 2
                    continue

                bare_header_match = bare_unit_header_pattern.match(line)
                if bare_header_match:
                    candidate_title = bare_header_match.group(2).strip()
                    if not is_repeat_of_current_title(candidate_title):
                        pending_title = candidate_title
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
                    create_unit(code_match.group(1), pending_title)
                    pending_title = ""
                    continue

                # Alternative reference formats (Qualification/Level) only when a title is pending
                if pending_title:
                    alt_match = alt_code_pattern.search(line)
                    if alt_match:
                        code_val = alt_match.group(1)
                        # Skip level-level codes like CONMS000L2
                        if not re.match(r'^[A-Z]{2,}/?[A-Z]{2,}0+L\d+$', code_val):
                            create_unit(code_val, pending_title)
                            pending_title = ""
                            continue

                # Direct code on its own line (rare edge case). Only trust this
                # when a unit title was just seen -- otherwise a code that
                # happens to wrap onto its own line inside the Mandatory Units
                # summary table (no title context at all) gets misread as the
                # start of a new, empty unit.
                if pending_title and re.match(r'^[A-Z]{2,}/[A-Z]{2,}/\d+/L\d+$', line):
                    create_unit(line.strip(), pending_title)
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
            unit_after_text = current_unit
            if last_creation_line_idx is not None:
                trailing_lines = lines[last_creation_line_idx + 1:]
                has_own_content_after = any(
                    re.match(r'^\d+\.\d+\b', l.strip()) or lo_pattern.search(l)
                    or 'PERFORMANCE CRITERIA' in l.upper()
                    for l in trailing_lines if l.strip()
                )
                if not has_own_content_after:
                    current_unit = unit_before_last_creation

            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            })

            for table in tables:
                # The "Mandatory/Optional Units" summary table (Unit Number /
                # Unit Reference Number / Unit Title / Credit Value / Guided
                # Learning Hours) is itself a clean, well-formed grid table
                # pdfplumber extracts like any other -- and since its rows
                # have neither an LO/PC marker nor cells that are pure header
                # fragments, they fall through the content_started gate
                # below as if they were real content, dumping the *next*
                # level's whole unit listing onto the last PC of the
                # previous unit. Its header cells "Unit Reference [Number]"
                # and "Unit Title" together are distinctive enough to catch
                # and skip the whole table.
                flat_cells = [str(c).upper() for row in table for c in row if c]
                if any("UNIT REFERENCE" in c for c in flat_cells) and any("UNIT TITLE" in c for c in flat_cells):
                    continue

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
                    
                    # Skip table headers and footers. These three checks catch
                    # the repeated header's three rows ("LEARNING .../
                    # PERFORMANCE CRITERIA ...", "OBJECTIVE (LO) / Type / Ref.
                    # Page", "The learner will: / The learner can: / No.")
                    # regardless of content_started, since on a long table
                    # split across a page break the header repeats *after*
                    # real content has already begun -- the content_started
                    # gate below only guards the table's very first header.
                    if any("LEARNING OBJECTIVE" in c.upper() or "PERFORMANCE CRITERIA" in c.upper() for c in clean_row):
                        continue
                    if any("OBJECTIVE (LO)" in c.upper() or "OBJECTIVE(LO)" in c.upper() for c in clean_row):
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

            # Hand off to whichever unit the text loop above landed on, so
            # the next page's tables (if that unit's content continues
            # there) attribute correctly.
            current_unit = unit_after_text

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
