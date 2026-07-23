import pdfplumber
import re
import json

pdf_path = "nosall/NOS-NSQ Agricultural equipment Mechanics Levels 2.pdf"

data = {
    "units": []
}

current_unit = None
current_lo = None
current_pc = None

unit_header_pattern = re.compile(r"^UNIT\s+\d+[:\s]*(.*)", re.IGNORECASE)
unit_code_pattern = re.compile(r"Unit Reference Number:\s*([A-Z0-9/]+)", re.IGNORECASE)
lo_pattern = re.compile(r"^(?:Learning\s*Outcome|LO)\.?\s*[:\s]*(\d+)\b(.*)", re.IGNORECASE)
pc_pattern = re.compile(r"^(?:PC\s+)?(\d+\.\d+)$", re.IGNORECASE)

STOP_KEYWORDS = ["NSQ LEVEL", "CREDIT VALUE", "UNIT PURPOSE", "ASSESSMENT", "GUIDED LEARNING", "OBJECTIVES:", "UNIT SECTOR", "THE LEARNER WILL", "QCF LEVEL", "THE LEARNER CAN", "MANDATORY UNITS", "OPTIONAL UNITS"]

with pdfplumber.open(pdf_path) as pdf:
    for page in pdf.pages:
        text = page.extract_text() or ""
        
        # 1. Process Text for Units
        lines = text.split('\n')
        pending_title = ""
        for line in lines:
            line = line.strip()
            if not line: continue
            
            header_match = unit_header_pattern.match(line)
            if header_match:
                pending_title = header_match.group(1).strip()
                continue
                
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
                continue
                
        # 2. Process Tables for LOs and PCs
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
        })
        
        lo_col_idx = 0
        for table in tables:
            for row in table:
                clean_row = [str(c).replace('\n', ' ').strip() if c is not None else "" for c in row]
                
                # Check for table headers like "LEARNING OBJECTIVE"
                if any("LEARNING OBJECTIVE" in c.upper() or "PERFORMANCE CRITERIA" in c.upper() for c in clean_row):
                    continue
                if any("The learner will:" in c for c in clean_row):
                    continue
                
                # Skip empty rows completely
                if not any(clean_row):
                    continue
                
                # A. Check for LO
                lo_found = False
                for c_idx, cell in enumerate(clean_row):
                    lo_match = lo_pattern.match(cell)
                    if lo_match:
                        lo_col_idx = c_idx
                        lo_num = lo_match.group(1)
                        desc = lo_match.group(2).strip()
                        # Clean up prefix like ":"
                        if desc.startswith(":"):
                            desc = desc[1:].strip()
                            
                        current_lo = {
                            "lo_num": lo_num,
                            "description": desc,
                            "performance_criteria": []
                        }
                        if current_unit is not None:
                            current_unit["learning_outcomes"].append(current_lo)
                        current_pc = None
                        clean_row[c_idx] = ""
                        lo_found = True
                        break
                        
                # B. Check for LO Description continuation
                if not lo_found and current_lo is not None and lo_col_idx < len(clean_row):
                    if clean_row[lo_col_idx]:
                        desc_part = clean_row[lo_col_idx]
                        if current_lo["description"]:
                            current_lo["description"] += " " + desc_part
                        else:
                            current_lo["description"] = desc_part
                        clean_row[lo_col_idx] = ""
                        
                # C. Check for PC Code
                pc_code = None
                for c_idx, cell in enumerate(clean_row):
                    pc_match = pc_pattern.match(cell)
                    if pc_match:
                        pc_code = pc_match.group(1)
                        # Remove all cells matching this PC code
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
                remaining_text = []
                for cell in clean_row:
                    if cell and cell not in remaining_text:
                        # Ignore stray table headers
                        if "Evidence" not in cell and "Type" not in cell and "Page No" not in cell and "Ref." not in cell and "Signature" not in cell and "Date:" not in cell:
                            remaining_text.append(cell)
                            
                if remaining_text:
                    text_to_add = " ".join(remaining_text)
                    if current_pc is not None:
                        if current_pc["description"]:
                            current_pc["description"] += " " + text_to_add
                        else:
                            current_pc["description"] = text_to_add
                    elif current_lo is not None:
                        if current_lo["description"]:
                            current_lo["description"] += " " + text_to_add
                        else:
                            current_lo["description"] = text_to_add

print(json.dumps(data, indent=2))
