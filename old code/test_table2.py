import pdfplumber
import re

pdf_path = "nosall/NOS-NSQ Agricultural equipment Mechanics Levels 2.pdf"
with pdfplumber.open(pdf_path) as pdf:
    for i in range(10, 20):
        page = pdf.pages[i]
        
        # Print text to see unit headers
        text = page.extract_text()
        print(f"--- PAGE {i} TEXT ---")
        for line in text.split('\n')[:10]: # print first 10 lines
            print(line)
        
        print(f"--- PAGE {i} TABLES ---")
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
        })
        for t_idx, table in enumerate(tables):
            print(f"Table {t_idx} (Rows: {len(table)}):")
            for r_idx, row in enumerate(table):
                # Clean row: replace None with "", replace newlines with space
                clean_row = [str(cell).replace('\n', ' ') if cell is not None else "" for cell in row]
                # Only print row if it has some non-empty content
                if any(clean_row):
                    print(f"  Row {r_idx}: {clean_row}")
