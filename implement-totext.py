import pdfplumber
import pathlib
import argparse

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

def process_directory_to_text_files(directory_path):
    path = pathlib.Path(directory_path)
    output_dir = path / "extracted_text"
    output_dir.mkdir(exist_ok=True)

    for pdf_file in path.glob("*.pdf"):
        try:
            print(f"Processing: {pdf_file.name}")
            text_data = extract_text_from_pdf(pdf_file)
            output_file = output_dir / f"{pdf_file.stem}.txt"
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(text_data)
            print(f"Saved to: {output_file}")
        except Exception as e:
            print(f"Error processing {pdf_file.name}: {e}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Extract raw text from NOS PDFs to individual text files.")
    parser.add_argument("--dir", default="./nosall", help="Directory containing the PDF files (default: ./nosall)")
    args = parser.parse_args()
    process_directory_to_text_files(args.dir)
