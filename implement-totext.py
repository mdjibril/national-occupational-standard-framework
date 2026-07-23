import pdfplumber
import pathlib
import argparse
import re

def extract_text_from_pdf(pdf_path):
    """Extracts raw text from each page of the PDF."""
    full_text = ""
    with pdfplumber.open(pdf_path) as pdf:
        for page in pdf.pages:
            text = page.extract_text(x_tolerance=2)
            if text:
                full_text += f"--- Page {page.page_number} ---\n"
                full_text += text + "\n\n"
    return full_text


def detect_levels_from_text(text, filename_stem):
    """Detect NSQ levels from unit codes in extracted text. Returns list of levels found."""
    levels = set()
    for m in re.finditer(r'/?L(\d+)', text):
        levels.add(int(m.group(1)))
    if not levels:
        m = re.search(r'Level[s]?\s*(\d+)', filename_stem, re.IGNORECASE)
        levels.add(int(m.group(1)) if m else 2)
    return sorted(levels)


def process_directory_to_text_files(directory_path):
    path = pathlib.Path(directory_path)
    base_output = pathlib.Path("extracted_text")

    for pdf_file in path.glob("*.pdf"):
        try:
            print(f"Processing: {pdf_file.name}")
            text_data = extract_text_from_pdf(pdf_file)
            levels = detect_levels_from_text(text_data, pdf_file.stem)

            for lvl in levels:
                output_dir = base_output / f"level-{lvl}"
                output_dir.mkdir(parents=True, exist_ok=True)
                output_file = output_dir / f"{pdf_file.stem}.txt"
                with open(output_file, 'w', encoding='utf-8') as f:
                    f.write(text_data)
                print(f"  Level {lvl} -> {output_file}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract raw text from NOS PDFs to individual text files.")
    parser.add_argument("--dir", default="./nosall", help="Directory containing the PDF files (default: ./nosall)")
    args = parser.parse_args()
    process_directory_to_text_files(args.dir)
