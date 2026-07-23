import pdfplumber

with pdfplumber.open("nosall/NOS-NSQ Agricultural equipment Mechanics Levels 2.pdf") as pdf:
    for i in range(10, 20):
        page = pdf.pages[i] 
        tables = page.extract_tables()
        for t_idx, table in enumerate(tables):
            print(f"Page {i} Table {t_idx}:")
            for r_idx, row in enumerate(table):
                print(f"  Row {r_idx}: {row}")
