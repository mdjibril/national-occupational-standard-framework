# Contributing to the NOS Framework

This project converts the Nigerian National Board for Technical Education (NBTE) National Occupational Standard (NOS) PDFs into structured JSON and plain text formats. Developers consuming these NOS datasets for web applications, LMS platforms, assessment tools, or skills registries depend on accurate extraction — your contribution helps make that possible.

---

## Setup

```bash
# Clone the repository
git clone https://github.com/<your-org>/national-occupational-standard-framework.git
cd national-occupational-standard-framework

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate      # Linux / macOS
# venv\Scripts\activate       # Windows

# Install the only dependency
pip install pdfplumber
```

---

## Contribution Workflow

At a high level the process is:

1. **Pick a NOS PDF** — find one on the NBTE portal (or elsewhere) that is not yet in the repo.
2. **Place it in `worker/`**.
3. **Convert** to JSON with the extraction script.
4. **Run `validate.py`** to check for structural issues, duplicate codes, and missing data.
5. **Verify** every unit, learning outcome, and performance criteria against the PDF.
6. **Fix any extraction gaps** in `implement-tojson.py` if the script misses data.
7. **Submit a pull request** when the output is clean.

---

## Step‑by‑Step Guide

### 1. Get the PDF

Download the NOS PDF from the public NBTE portal:

🔗 [https://www.digitalnbte.nbte.gov.ng/Public/PUCNOS](https://www.digitalnbte.nbte.gov.ng/Public/PUCNOS)

**Naming convention** — Rename the downloaded file before placing it in `worker/`:

- Regular trades: `"NOS Course Name"` (e.g., `"NOS Painting and Decoration.pdf"`)
- ICT courses: `"NOS ICT Course Name"` (e.g., `"NOS ICT Cybersecurity Engineering L5.pdf"`)

Then copy your PDF into the `worker/` directory:

```bash
cp ~/Downloads/NOS\ Painting\ and\ Decoration.pdf ./worker/
```

### Already Extracted Trades

These NOS have already been converted to JSON. Pick a trade **not** listed here to avoid duplicating work.

| Trade | L1 | L2 | L3 | L4 | L5 |
|---|---|---|---|---|---|
| Agricultural Equipment Mechanics | ✅ | ✅ | ✅ | | |
| Aluminium Cladding | ✅ | ✅ | ✅ | ✅ | ✅ |
| Animal Husbandry (Livestock Farming) | ✅ | ✅ | ✅ | | |
| Autobody Works | ✅ | ✅ | ✅ | | |
| Automobile Mechanics | ✅ | ✅ | ✅ | | |
| Blacksmithing | ✅ | ✅ | ✅ | | |
| Carpentry and Joinery | ✅ | ✅ | ✅ | | |
| Cosmetology and Beauty Therapy | ✅ | ✅ | ✅ | | |
| Electrical Installation Maintenance and Repairs | ✅ | ✅ | ✅ | | |
| Fashion and Garment Making | ✅ | ✅ | ✅ | | |
| Fish Farming Activity (Aquaculture) | ✅ | ✅ | ✅ | | |
| Furniture Making and Upholstery | ✅ | ✅ | ✅ | | |
| ICT Back-End Web Development | | | ✅ | | |
| ICT CAD CAM | | | ✅ | | |
| ICT Cinematography | | | ✅ | | |
| ICT Computer Hardware Repairs & Maintenance | ✅ | ✅ | ✅ | | |
| ICT Computer Networking | ✅ | ✅ | ✅ | | |
| ICT Computer Operation | | ✅ | | | |
| ICT Creative Media Production | ✅ | ✅ | ✅ | | |
| ICT Cybersecurity Analyst | | | ✅ | | |
| ICT Cybersecurity Engineering | | | | | ✅ |
| ICT Data Analytics | | | | ✅ | |
| ICT Digital Content Creation | | | ✅ | | |
| ICT Digital Service Operations | | ✅ | ✅ | | |
| ICT Front-End Web Development | | | ✅ | | |
| ICT Mobile App Development | | | | | ✅ |
| ICT Mobile Phone RM | | ✅ | | | |
| ICT Network Cabling, Installation and Maintenance | | ✅ | | | |
| ICT Network Support Specialist | | | | ✅ | |
| ICT Programming with PHP using Laravel and MySql | | | | | ✅ |
| ICT Social Media Communication | | | ✅ | | |
| ICT Social Media Contents Creation and Management | ✅ | ✅ | ✅ | | |
| ICT Web Development | | ✅ | ✅ | ✅ | |
| Leather Works | ✅ | ✅ | ✅ | | |
| Masonry | ✅ | ✅ | ✅ | | |
| Painting and Decoration | ✅ | ✅ | ✅ | | |
| Plumbing | ✅ | ✅ | ✅ | | |
| Refrigeration and Air Conditioning | ✅ | ✅ | ✅ | | |
| Solar Photovoltaic System Installation and Maintenance | ✅ | ✅ | ✅ | | |
| Tilling and Decorative Stonework | ✅ | ✅ | ✅ | | |
| Tire and Wheel Services | ✅ | ✅ | ✅ | | |
| Traditional Medicine Practice | ✅ | ✅ | | | |
| Welding and Fabrication Levels | ✅ | ✅ | ✅ | | |

### 2. Run the extraction scripts

```bash
# Convert PDF → JSON (auto‑detects NSQ level and splits into appropriate level‑N/ folders)
python implement-tojson.py --dir ./worker

```

Output is written to:

```
extracted_json/
  level-1/
  level-2/
  level-3/
```

A single PDF that spans multiple NSQ levels (common for masonry and other trades) will produce one file per level, each containing only the units belonging to that level.

### 3. Run the validator

Before manual review, run the validator to catch structural issues automatically:

```bash
# Validate everything
python validate.py extracted_json/

# Validate a single level
python validate.py extracted_json/level-2/

# Validate a specific file
python validate.py extracted_json/level-2/"NOS Painting and decoration.json"
```

The validator checks for:
- **Structural integrity** — missing keys, wrong types.
- **Unit code format** — valid patterns and OCR errors (letter `O` instead of `0`).
- **Level consistency** — unit codes match their document level.
- **Numbering gaps** — missing LOs or PCs in a sequence.
- **Duplicates** — repeated unit codes, LO numbers, or PC codes.
- **Empty descriptions** — trade names, unit titles, LOs, or PCs that may have been missed.

Fix any errors before moving on. Warnings (empty descriptions, OCR suspicion) are acceptable if verified manually against the source PDF.

### 4. Verify the JSON output

Open the generated JSON and the original PDF side by side. For **every unit** check:

- **Unit code** — matches `Unit Reference Number` in the PDF.
- **Unit title** — matches the title in the PDF.
- **Learning outcomes** — every LO from the PDF is present with the correct number.
- **Performance criteria** — every PC (e.g., `1.2`, `3.4`) is present under the correct LO with a complete description.
- **PC descriptions** — no truncated text, no mixed‑up columns, no garbage from table headers.

A quick way to count PCs in your output:

```bash
python -c "
import json
with open('extracted_json/level-2/NOS-NSQ New Trade Levels 2.json') as f:
    data = json.load(f)
for u in data['units']:
    pcs = sum(len(lo['performance_criteria']) for lo in u['learning_outcomes'])
    print(f'{u[\"code\"]}: {len(u[\"learning_outcomes\"])} LOs, {pcs} PCs')
"
```

If any unit, LO, or PC is missing, move to step 5. If everything checks out, skip to step 6.

### 5. What to do when extraction misses data

The extraction script (`implement-tojson.py`) handles the most common PDF layouts, but NBTE PDFs vary in formatting. Common issues you may encounter:

| Problem | Likely cause | Where to look |
|---|---|---|
| Entire unit missing | `Unit Reference Number` format not recognised | `unit_code_pattern` regex (line ~9) |
| Unit title is "Unknown Title" | `Unit Title:` line uses a different delimiter | `unit_title_pattern` regex or text processing loop |
| Learning outcomes not detected | Table layout differs from expected columns | Table processing logic (line ~130+) |
| Some PCs end up under the wrong LO | PC code prefix auto‑switch not working | `get_or_create_lo()` call in PC section |
| Multi‑page tables lose data | Table extraction doesn't carry state across pages | The `current_lo` / `current_pc` variables |

If you are comfortable with Python regex and `pdfplumber`, please include the fix in your PR. If not, open an issue describing what is missing and attach the PDF — someone else can work on the extraction logic.

### 6. Clean up and PR

- Remove the source PDF from `worker/` — only the extracted JSON and text files should be committed.
- Delete any stale files in `worker/extracted_json/` left over from earlier runs.

```bash
rm worker/NOS-NSQ\ New\ Trade\ Levels\ 2.pdf
rm -rf worker/extracted_json/ 
```

- Commit only the new `extracted_json/` files:

```bash
git add extracted_json/ 
git commit -F - <<'EOF'
Add NOS extraction for New Trade Level 2

Co-authored-by: YourName <noreply@commandcode.ai>
EOF
```

- Push your branch and open a pull request. In the PR description, mention which PDF you processed and confirm that you verified all units, LOs, and PCs manually.

---

## Script Reference

### `implement-tojson.py`

- **What it does** — Parses NOS PDFs with `pdfplumber`, extracting trade names, unit codes/titles, learning outcomes, and performance criteria into structured JSON.
- **CLI flags**:
  - `--dir` — Directory containing the PDFs (default: `./worker`).
  - `--trade` — Override the auto‑detected trade name.
- **Level detection** — Units are split by the `/L1`, `/L2`, `/L3` suffix in their reference codes. A multi‑level PDF produces a separate JSON file for each level.

---

## Data Model

The JSON follows this hierarchy:

```
{
  "trade_name": "PAINTING AND DECORATION",
  "level": 2,
  "units": [
    {
      "code": "CON/PD/004/L2",
      "title": "Handling and Storage of Painting and decorating materials",
      "learning_outcomes": [
        {
          "lo_num": "1",
          "description": "Handle Painting and Decorating materials",
          "performance_criteria": [
            {
              "pc_code": "1.1",
              "description": "Identify methods of safe handling..."
            }
          ]
        }
      ]
    }
  ]
}
```

---

## Avoiding Common Mistakes

- **Do not guess levels**. Let the script auto‑detect — each unit's code contains its NSQ level.
- **Hand‑editing JSON is acceptable for small, obvious fixes**. Examples:
  - A unit code missing `/` separators (`CONPD004L2` → `CON/PD/004/L2`).
  - Stray PDF text that leaked into a description (e.g., `"NSQ level: 2 Credit value: 4"` appended to a PC).
  - An LO description that picked up a page number or footer text.
  - A trade name that auto‑detection got wrong (e.g., `"// PAINTING AND DECORATION // LEVEL 1 - 3"` → `"PAINTING AND DECORATION"`).

  If you can clearly trace the error by comparing the JSON to the PDF, go ahead and fix it. For anything larger — missing units, whole sections absent, wrong LO/PC assignments — fix the extraction script instead and re‑run. Always note manual edits in your PR description.
- **Check empty descriptions**. Some PDF layouts put LO descriptions on separate lines or interleaved with PC text. A few empty LO descriptions are acceptable when the PDF layout makes clean extraction impossible — PCs are what really matter.
- **Do not skip the text output**. The `.txt` files are useful for debugging extraction issues — compare them against the JSON to find gaps.
- **One trade per PDF**. Most NOS PDFs contain a single trade. If your PDF covers multiple trades, split it or note it in your PR.

---

## Questions & Support

For questions, clarifications, or suggestions, reach out at:

- **muhammadjibrildauda@gmail.com**
