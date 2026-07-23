
#!/usr/bin/env python3
"""
Extract NOS-style PDF content into:
  1) a strict JSON structure
  2) a cleaned text file

Outputs one JSON and one TXT per PDF in the input directory.
"""

import argparse
import json
import pathlib
import re
from typing import Dict, List, Tuple, Optional

import pdfplumber


UNIT_TITLE_RE = re.compile(r"^\s*Unit\s+(\d+)\s*[:\-]\s*(.+?)\s*$", re.I)
UNIT_CODE_RE = re.compile(r"Unit\s+reference\s+number\s*:\s*([A-Z0-9/]+)", re.I)
LO_HEADER_RE = re.compile(r"^\s*LO\.?\s*(\d+)\s*[:\-]?\s*(.*)$", re.I)
PC_CODE_RE = re.compile(r"(?<!\d)(\d+\.\d+)\b")

NOISE_PATTERNS = [
    r"^\s*\d+\s*$",
    r"^\s*page\s*\d+\s*$",
    r"^\s*learners?\s+signature\b.*$",
    r"^\s*assessors?\s+signature\b.*$",
    r"^\s*iqa\s+signature\b.*$",
    r"^\s*eqa\s+signature\b.*$",
    r"^\s*evidence\s+type\b.*$",
    r"^\s*evidence\s+ref\.?\b.*$",
    r"^\s*page\s*no\.?\b.*$",
    r"^\s*the\s+learner\s+will:\s*$",
    r"^\s*the\s+learner\s+can:\s*$",
]
NOISE_RES = [re.compile(p, re.I) for p in NOISE_PATTERNS]


def normalize(text: str) -> str:
    text = text.replace("ﬁ", "fi").replace("ﬂ", "fl")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def clean_fragment(text: str) -> str:
    text = normalize(text)
    text = re.sub(r"^[\s:.\-]+", "", text)
    text = re.sub(r"\b(?:Page\s*\d+|\d+)\b$", "", text, flags=re.I).strip()
    return text


def is_noise(text: str) -> bool:
    t = normalize(text)
    if not t:
        return True
    u = t.upper()
    if "NATIONAL SKILLS QUALIFICATION" in u:
        return True
    return any(rx.match(t) for rx in NOISE_RES)


def append_text(base: str, addition: str) -> str:
    addition = clean_fragment(addition)
    if not addition:
        return base
    if not base:
        return addition
    if base.endswith(addition):
        return base
    if len(addition) > 8 and addition in base:
        return base
    return normalize(base + " " + addition)


def cluster_words(words: List[Dict], tol: float = 2.4) -> List[Dict]:
    rows: List[Dict] = []
    for w in sorted(words, key=lambda x: (x["top"], x["x0"])):
        for row in rows:
            if abs(row["top"] - w["top"]) <= tol:
                row["words"].append(w)
                row["top"] = sum(x["top"] for x in row["words"]) / len(row["words"])
                break
        else:
            rows.append({"top": w["top"], "words": [w]})
    rows.sort(key=lambda r: r["top"])
    for row in rows:
        row["words"].sort(key=lambda w: w["x0"])
    return rows


def row_text(words: List[Dict]) -> str:
    return normalize(" ".join(w["text"] for w in words))


def split_lr(words: List[Dict], split_x: float = 175) -> Tuple[List[Dict], List[Dict]]:
    left = [w for w in words if w["x0"] < split_x]
    right = [w for w in words if w["x0"] >= split_x]
    return left, right


def extract_trade_name(page) -> str:
    rows = cluster_words(page.extract_words())
    for row in rows[:10]:
        text = row_text(row["words"])
        if "NATIONAL SKILLS QUALIFICATION" in text.upper():
            tail = re.sub(r"^.*?NATIONAL SKILLS QUALIFICATION\s*", "", text, flags=re.I).strip()
            if tail:
                return tail
    for row in rows[:15]:
        text = row_text(row["words"])
        if not text or is_noise(text):
            continue
        if len(text) <= 90 and text.upper() == text and not text.startswith("Unit "):
            return text
    return ""


def new_unit(title: str = "", code: str = "") -> Dict:
    return {"code": code or "", "title": title or "", "learning_outcomes": []}


def get_or_create_unit(data: Dict, title: Optional[str] = None, code: Optional[str] = None) -> Dict:
    if code:
        for u in data["units"]:
            if u["code"] == code:
                if title and not u["title"]:
                    u["title"] = title
                return u
    if title:
        for u in data["units"]:
            if u["title"] == title and (not code or not u["code"]):
                if code:
                    u["code"] = code
                return u
    unit = new_unit(title or "", code or "")
    data["units"].append(unit)
    return unit


def get_lo(unit: Dict, lo_num: str) -> Dict:
    lo_num = str(lo_num)
    for lo in unit["learning_outcomes"]:
        if lo["lo_num"] == lo_num:
            return lo
    lo = {"lo_num": lo_num, "description": "", "performance_criteria": []}
    unit["learning_outcomes"].append(lo)
    return lo


def get_pc(lo: Dict, pc_code: str) -> Dict:
    for pc in lo["performance_criteria"]:
        if pc["pc_code"] == pc_code:
            return pc
    pc = {"pc_code": pc_code, "description": ""}
    lo["performance_criteria"].append(pc)
    return pc


def process_pc_source(source_text: str, current_unit: Dict, current_lo: Optional[Dict], left_text: str = "") -> Tuple[Optional[Dict], Optional[Dict]]:
    matches = list(PC_CODE_RE.finditer(source_text))
    if not matches:
        return current_lo, None

    current_pc = None
    left_text = clean_fragment(left_text)
    if left_text and current_lo is not None and not re.fullmatch(r"\d+", left_text):
        current_lo["description"] = append_text(current_lo["description"], left_text)

    for idx, m in enumerate(matches):
        pc_code = m.group(1)
        lo_num = pc_code.split(".")[0]
        if current_lo is None or current_lo["lo_num"] != lo_num:
            current_lo = get_lo(current_unit, lo_num)
        current_pc = get_pc(current_lo, pc_code)

        start = m.end()
        end = matches[idx + 1].start() if idx + 1 < len(matches) else len(source_text)
        desc = clean_fragment(source_text[start:end])
        if desc:
            current_pc["description"] = append_text(current_pc["description"], desc)

    return current_lo, current_pc


def parse_pdf(pdf_path: pathlib.Path, trade_name: Optional[str] = None) -> Tuple[Dict, str]:
    data = {"trade_name": trade_name or "", "units": []}
    cleaned_pages: List[str] = []

    current_unit = None
    current_lo = None
    current_pc = None

    with pdfplumber.open(str(pdf_path)) as pdf:
        if not data["trade_name"] and pdf.pages:
            data["trade_name"] = extract_trade_name(pdf.pages[0])

        for page in pdf.pages:
            rows = cluster_words(page.extract_words())
            page_lines: List[str] = []

            for row in rows:
                text = row_text(row["words"])
                if is_noise(text):
                    continue

                left_words, right_words = split_lr(row["words"])
                left_text = row_text(left_words)
                right_text = row_text(right_words)

                # Unit title row
                m_title = UNIT_TITLE_RE.match(text)
                if m_title:
                    title = normalize(m_title.group(2))
                    current_unit = get_or_create_unit(data, title=title, code=None)
                    current_lo = None
                    current_pc = None
                    page_lines.append(text)
                    continue

                # Unit reference row
                m_code = UNIT_CODE_RE.search(text)
                if m_code:
                    code = m_code.group(1).strip()
                    if current_unit is None:
                        current_unit = get_or_create_unit(data, title=None, code=code)
                    else:
                        current_unit["code"] = code
                    current_lo = None
                    current_pc = None
                    page_lines.append(text)
                    continue

                # LO header row
                m_lo = LO_HEADER_RE.match(text)
                if m_lo and current_unit is not None:
                    lo_num = m_lo.group(1)
                    current_lo = get_lo(current_unit, lo_num)
                    current_pc = None

                    source = normalize(m_lo.group(2))
                    if source:
                        pc_first = PC_CODE_RE.search(source)
                        if pc_first:
                            pre = clean_fragment(source[:pc_first.start()])
                            if pre:
                                current_lo["description"] = append_text(current_lo["description"], pre)
                            current_lo, current_pc = process_pc_source(source, current_unit, current_lo)
                        else:
                            current_lo["description"] = append_text(current_lo["description"], source)

                    page_lines.append(text)
                    continue

                # Any row that contains PCs
                if PC_CODE_RE.search(right_text or text) and current_unit is not None:
                    src = right_text if PC_CODE_RE.search(right_text) else text
                    current_lo, current_pc = process_pc_source(src, current_unit, current_lo, left_text=left_text)
                    page_lines.append(text)
                    continue

                # Continuation rows without PCs
                if current_pc is not None and not left_text and right_text:
                    current_pc["description"] = append_text(current_pc["description"], right_text)
                    page_lines.append(text)
                    continue

                if current_lo is not None:
                    combined = f"{left_text} {right_text}".strip()
                    if combined:
                        current_lo["description"] = append_text(current_lo["description"], combined)
                    page_lines.append(text)
                    continue

                page_lines.append(text)

            cleaned_pages.append("\n".join(page_lines))

    # Final cleanup
    for unit in data["units"]:
        unit["learning_outcomes"] = [
            lo for lo in unit["learning_outcomes"]
            if lo["description"] or lo["performance_criteria"]
        ]
        for lo in unit["learning_outcomes"]:
            lo["performance_criteria"] = [
                pc for pc in lo["performance_criteria"]
                if pc["description"] or pc["pc_code"]
            ]

    return data, "\n\n".join(cleaned_pages)


def process_directory(directory_path: str, trade_name: Optional[str] = None) -> None:
    base = pathlib.Path(directory_path)
    json_dir = base / "extracted_json"
    txt_dir = base / "extracted_text"
    json_dir.mkdir(exist_ok=True)
    txt_dir.mkdir(exist_ok=True)

    pdf_files = sorted(base.glob("*.pdf"))
    for pdf_file in pdf_files:
        print(f"Processing: {pdf_file.name}")
        try:
            data, cleaned_text = parse_pdf(pdf_file, trade_name=trade_name)

            json_path = json_dir / f"{pdf_file.stem}.json"
            txt_path = txt_dir / f"{pdf_file.stem}.txt"

            with open(json_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(cleaned_text)

            print(f"Saved: {json_path}")
            print(f"Saved: {txt_path}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Extract NOS curriculum data from PDFs to JSON and cleaned text files."
    )
    parser.add_argument("--dir", default="./nosall", help="Directory containing PDF files.")
    parser.add_argument("--trade", help="Optional override for trade name.")
    args = parser.parse_args()

    process_directory(args.dir, trade_name=args.trade)


if __name__ == "__main__":
    main()
