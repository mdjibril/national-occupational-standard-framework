import pdfplumber

with pdfplumber.open("nosall/NOS-NSQ Agricultural equipment Mechanics Levels 2.pdf") as pdf:
    for page in pdf.pages[2:6]: 
        tables = page.extract_tables(table_settings={
            "vertical_strategy": "lines",
            "horizontal_strategy": "lines",
            "snap_tolerance": 3,
            "join_tolerance": 3,
        })
        for i, t in enumerate(tables):
            print(f"Page {page.page_number} Table {i}")
            for r in t:
                print([str(c).replace('\n', ' ').strip() if c is not None else "" for c in r])
