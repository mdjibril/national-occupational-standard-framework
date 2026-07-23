import pdfplumber
import json
import re
import pathlib
import argparse

def parse_pdf_to_json(pdf_path, trade_name=None):
    unit_header_pattern = re.compile(r"^UNIT\s+\d+[:\s]*(.*)", re.IGNORECASE)
    unit_code_pattern = re.compile(r"Unit Reference Number:\s*([A-Z0-9/]+)", re.IGNORECASE)
    # Matches "LO 1" or "Learning Outcome 1"
    lo_pattern = re.compile(r"(?:Learning\s*Outcome|LO)\.?\s*[:\s]*(\d+)\b", re.IGNORECASE)
    # Matches "PC 1.1" or just "1.1"
    pc_pattern = re.compile(r"(?:PC\s+)?(\d+\.\d+)(?:\s*[:\s]*(.*))?", re.IGNORECASE)

    # Keywords that signal the end of a Unit Title and the start of metadata
    STOP_KEYWORDS = ["NSQ LEVEL", "CREDIT VALUE", "UNIT PURPOSE", "ASSESSMENT", "GUIDED LEARNING", "OBJECTIVES:", "UNIT SECTOR", "THE LEARNER WILL", "QCF LEVEL", "THE LEARNER CAN", "MANDATORY UNITS", "OPTIONAL UNITS"]

    # "Describe the table" - Settings for the table extraction engine
    TABLE_SETTINGS = {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 3,
        "join_tolerance": 3,
    }

    data = {
        "trade_name": trade_name,
        "units": []
    }

    current_unit = None
    current_lo = None
    current_pc = None
    pending_title = ""
    title_finalized = False
    expecting_lo_description = False

    with pdfplumber.open(pdf_path) as pdf:
        # Rule: Locate overall trade name if generic or not provided
        if not trade_name:
            first_page_text = pdf.pages[0].extract_text()
            if first_page_text:
                # Extract dynamic trade name (Top Right) while ignoring Top Left header
                lines = [l.strip() for l in first_page_text.split('\n') if l.strip()]
                for line in lines:
                    # Clean out the generic qualification name to find the specific trade
                    clean_line = re.sub(r"NATIONAL SKILLS QUALIFICATION", "", line, flags=re.IGNORECASE).strip()
                    # Skip page numbers or empty results
                    if clean_line and not clean_line.isdigit():
                        data["trade_name"] = clean_line
                        break
                if not data["trade_name"] and lines:
                    data["trade_name"] = lines[0]

        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2) or ""

            lines = text.split('\n')
            for line in lines:
                line = line.strip()

                # Aggressive filtering of headers/footers found in your samples
                if not line or re.match(r"^(Page\s+\d+|[0-9]+|No\.|Evidence|Evidence\s*Type|Ref\.|Page\s*Number|LEARNING\s*OBJECTIVE.*|PERFORMANCE\s*CRITERIA.*)$", line, re.IGNORECASE):
                    continue
                
                # Dynamic Header Filter: Ignore the Qualification name and Detected Trade Name found on every page
                upper_line = line.upper()
                if "NATIONAL SKILLS QUALIFICATION" in upper_line:
                    continue
                if data["trade_name"] and data["trade_name"].upper() in upper_line:
                    continue
                
                if "Learner’s Signature" in line or "Assessors Signature" in line or "Date:" in line:
                    continue
                
                if any(k in line.upper() for k in STOP_KEYWORDS):
                    title_finalized = True
                    continue
                
                # 1. Look for Unit Header (Title)
                header_match = unit_header_pattern.match(line)
                if header_match:
                    # If we found a new header while processing, finalize the previous unit's title
                    if current_unit and not title_finalized:
                        title_finalized = True
                        
                    pending_title = header_match.group(1).strip()
                    title_finalized = False
                    continue

                # 2. Look for Unit Code (This confirms we are on a detail page)
                code_match = unit_code_pattern.search(line)
                if code_match:
                    current_unit = {
                        "code": code_match.group(1),
                        "title": pending_title if pending_title else "Unknown Title",
                        "learning_outcomes": []
                    }
                    data["units"].append(current_unit)
                    current_lo = None
                    current_pc = None
                    pending_title = ""
                    title_finalized = False
                    continue

                # 3. Detect Learning Outcome (Start of a new LO block)
                lo_match = lo_pattern.search(line)
                if lo_match and current_unit is not None:
                    lo_id = lo_match.group(1)
                    current_lo = {
                        "lo_num": lo_id,
                        "description": "",
                        "performance_criteria": []
                    }
                    current_unit["learning_outcomes"].append(current_lo)
                    current_pc = None
                    # After 'LO X:', the text immediately following (on same or next lines) is the description
                    desc_part = line[lo_match.end():].strip()
                    if desc_part:
                        # Split to avoid capturing PC content if it started on the same line
                        parts = re.split(r'\s{2,}', desc_part)
                        current_lo["description"] = parts[0].strip()
                    continue

                pc_match = pc_pattern.search(line)
                if pc_match and current_lo is not None:
                    pc_lo_id = pc_match.group(1).split('.')[0]
                    
                    # Auto-transition LO state based on PC prefix (e.g., PC 2.1 transitions to LO 2)
                    if pc_lo_id != current_lo["lo_num"]:
                        existing_lo = next((l for l in current_unit["learning_outcomes"] if l["lo_num"] == pc_lo_id), None)
                        if existing_lo:
                            current_lo = existing_lo
                        else:
                            current_lo = {"lo_num": pc_lo_id, "description": "", "performance_criteria": []}
                            current_unit["learning_outcomes"].append(current_lo)
                    
                    # If PC belongs to a different LO, try to find it or create it
                    if pc_lo_id != current_lo["lo_num"]:
                        existing_lo = next((l for l in current_unit["learning_outcomes"] if l["lo_num"] == pc_lo_id), None)
                        current_lo = existing_lo if existing_lo else current_lo

                    # Process the PC line
                    pc_text_raw = pc_match.group(2) or ""
                    parts = re.split(r'\s{2,}', pc_text_raw.strip())
                    
                    current_pc = {
                        "pc_code": pc_match.group(1),
                        "description": parts[0].strip()
                    }
                    current_lo["performance_criteria"].append(current_pc)
                    
                    # Heuristic: Text to the LEFT of a PC code in a linearized table belongs to the LO description
                    text_before_pc = line[:pc_match.start()].strip()
                    if text_before_pc:
                        current_lo["description"] = (current_lo["description"] + " " + text_before_pc).strip()
                    continue

                # 4. Table Body Continuation Logic
                # In linearized table text: Left Part = LO Description, Right Part = PC Description
                parts = re.split(r'\s{2,}', line)
                
                if current_pc:
                    # If there's a split, the first part is likely LO text wrapping, second is PC text wrapping
                    if len(parts) > 1:
                        current_lo["description"] = (current_lo["description"] + " " + parts[0]).strip()
                        current_pc["description"] = (current_pc["description"] + " " + parts[1]).strip()
                    else:
                        # If no split, assume it's continuing the PC description
                        current_pc["description"] = (current_pc["description"] + " " + parts[0]).strip()
                elif current_lo:
                    # Continue LO description if no PC is active yet
                    current_lo["description"] = (current_lo["description"] + " " + parts[0]).strip()
                elif not title_finalized:
                    if pending_title:
                        pending_title = (pending_title.rstrip() + " " + line).strip()
                    elif current_unit:
                        current_unit["title"] = (current_unit["title"].rstrip() + " " + line).strip()

    return data

def process_directory_to_individual_jsons(directory_path, trade_name=None):
    path = pathlib.Path(directory_path)
    output_dir = path / "extracted_json"
    output_dir.mkdir(exist_ok=True)

    for pdf_file in path.glob("*.pdf"):
        try:
            print(f"Processing: {pdf_file.name}")
            file_data = parse_pdf_to_json(pdf_file, trade_name)
            output_file = output_dir / f"{pdf_file.stem}.json"
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(file_data, f, indent=2)
            print(f"Saved to: {output_file}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract NOS curriculum data from PDFs to individual JSON files.")
    parser.add_argument("--dir", default="./nosall", help="Directory containing the PDF files (default: ./nosall)")
    parser.add_argument("--trade", help="Optional: Override the trade name for all files. If omitted, it is auto-detected from the PDF.")
    
    args = parser.parse_args()
    process_directory_to_individual_jsons(args.dir, args.trade)
