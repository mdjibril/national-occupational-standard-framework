import pdfplumber
import json
import re
import pathlib
import argparse

def parse_pdf_to_json(pdf_path, trade_name=None):
    unit_header_pattern = re.compile(r"^UNIT\s+\d+[:\s]*(.*)", re.IGNORECASE)
    unit_code_pattern = re.compile(r"Unit Reference Number:?\s*([A-Z0-9/]+)", re.IGNORECASE)
    unit_title_pattern = re.compile(r"Unit Title:\s*(.*)", re.IGNORECASE)
    lo_pattern = re.compile(r"(?:Learning\s*Outcome|LO)\.?\s*[:\s]*(\d+)\b", re.IGNORECASE)
    pc_pattern = re.compile(r"^(?:PC\s+)?(\d+\.\d+)$", re.IGNORECASE)

    data = {
        "trade_name": trade_name,
        "units": []
    }

    current_unit = None
    current_lo = None
    current_pc = None
    last_pc_col_idx = 999

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
                for line in lines:
                    clean_line = re.sub(r"NATIONAL SKILLS QUALIFICATION", "", line, flags=re.IGNORECASE).strip()
                    if clean_line and not clean_line.isdigit():
                        data["trade_name"] = clean_line
                        break
                if not data["trade_name"] and lines:
                    data["trade_name"] = lines[0]

        for page in pdf.pages:
            text = page.extract_text() or ""
            
            # 1. Process Text for Units
            lines = text.split('\n')
            pending_title = ""
            pending_code_line = False
            for line in lines:
                line = line.strip()
                if not line: continue
                
                # Handle multi-line reference numbers (code on next line)
                if pending_code_line:
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
                    continue
                
                # Capture separate Unit Title: lines
                title_match = unit_title_pattern.search(line)
                if title_match:
                    pending_title = title_match.group(1).strip()
                    continue
                    
                # Check if this line is just "Unit Reference Number:" with code on next line
                if re.search(r'Unit Reference Number:?\s*$', line, re.IGNORECASE):
                    pending_code_line = True
                    continue
                
                code_match = unit_code_pattern.search(line)
                if code_match:
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
                
                # Direct code on its own line (rare edge case)
                if re.match(r'^[A-Z]{2,}/[A-Z]{2,}/\d+/L\d+$', line):
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

            # 2. Process Tables for LOs and PCs
            tables = page.extract_tables(table_settings={
                "vertical_strategy": "lines",
                "horizontal_strategy": "lines",
                "snap_tolerance": 3,
                "join_tolerance": 3,
            })
            
            for table in tables:
                for row in table:
                    clean_row = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                    
                    # Skip table headers and footers
                    if any("LEARNING OBJECTIVE" in c.upper() or "PERFORMANCE CRITERIA" in c.upper() for c in clean_row):
                        continue
                    if any("THE LEARNER WILL" in c.upper() or "THE LEARNER CAN" in c.upper() for c in clean_row):
                        continue
                    if any("SIGNATURE" in c.upper() for c in clean_row):
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
    parser.add_argument("--dir", default="./worker", help="Directory containing the PDF files (default: ./worker)")
    parser.add_argument("--trade", help="Optional: Override the trade name for all files. If omitted, it is auto-detected from the PDF.")
    
    args = parser.parse_args()
    process_directory_to_individual_jsons(args.dir, args.trade)
