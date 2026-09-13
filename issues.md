The `validate.py` run on `extracted_json/level-3/` shows **109 errors** and **50 warnings** across **25 files** (out of 34 total). These issues need manual review against the source PDFs — anyone willing to help is welcome!

## Files with Issues

| File | Errors | Warnings | Key Problems |
|------|--------|----------|--------------|
| **ICT Digital Service Operations L3** | 16 | 9 | All 13 units have LevelRule violations (document level is L2 but unit codes say L3); duplicate PCs 2.1-2.3; multiple empty descriptions |
| **Furniture Making & Upholstery** | 13 | 0 | All PCs duplicated in Unit 3 LOs 1-3 (10 PCs); missing PCs 2.4, 2.5, 5.2 |
| **Masonry** | 11 | 3 | Bad code `CON/MS001/L3` missing slash; PC numbering gaps in Units 1, 2, 4, 6, 7 (missing .1 starts, missing 2.1, 3.1, 3.3, 3.2) |
| **Welding & Fabrication Levels** | 11 | 0 | Unit codes 001-003/L3 duplicated 3 times (Units 12-14, 18-20, 23-25); missing PC 2.9; duplicate PC 3.8 |
| **Painting & Decoration** | 8 | 10 | Missing PCs across 6 LOs (1.5, 3.4, 3.3, 3.4, 2.2, 2.4, 2.4); duplicate PC 4.4; 10 empty descriptions including 2 PC descriptions |
| **Cosmetology & Beauty Therapy** | 7 | 3 | Bad code `CBT/COS/OO4/L3` (O-not-zero); entire LO 4 duplicated (4 PCs); duplicate PC 3.5; empty PC list (Unit 10 LO 3) |
| **Agricultural Equipment Mechanics** | 6 | 1 | Duplicate PCs 3.1-3.3 + 7.2; empty PC lists (Unit 2 LO 4, Unit 10 LO 3) |
| **Leather Works** | 5 | 4 | Bad code `FLW/LWK/OO4/L3`; missing PCs 4.5, 3.4; PC numbering broken LO 3; 3 empty LOs |
| **Refrigeration & AC** | 5 | 1 | Missing PC 3.5; PC numbering broken LO 4 (no 4.1); duplicate PC 4.2; empty PC list (Unit 9 LO 4) |
| **Tire & Wheel Services** | 5 | 4 | PCs 3.2-3.5 duplicated; PC 4.2 duplicated; 4 empty PC descriptions |
| **ICT Front-End Web Development** | 4 | 0 | PC numbering starts wrong on LO 3; duplicate PCs 1.2, 2.1 |
| **ICT Back-End Web Development** | 3 | 0 | Missing PC 2.3; duplicate PCs 1.8, 1.5 |
| **Tilling & Decorative Stonework** | 3 | 0 | Missing PCs 1.3, 3.4, 3.5 |
| **Automobile Mechanics** | 2 | 2 | Duplicate PCs 3.4, 2.5; 2 empty LO descriptions |
| **ICT Cybersecurity Analyst** | 2 | 0 | Missing PC 4.16; duplicate PC 3.1 |
| **Plumbing** | 2 | 8 | Bad codes `CON/PL/OO4/L3`, `CON/PL/OO5/L3` (O-not-zero); 6 empty LO descriptions |
| **Animal Husbandry** | 1 | 0 | LevelRule violation (Unit 7 L2 code in L3 doc) |
| **Blacksmithing** | 1 | 0 | Missing LO 4 in Unit 2 |
| **Carpentry & Joinery** | 1 | 0 | Duplicate PC 3.3 |
| **Electrical Installation** | 1 | 3 | Duplicate PC 1.1; 3 empty LO descriptions |
| **ICT Computer Networking** | 1 | 0 | PC numbering starts wrong on LO 2 |
| **ICT Digital Content Creation** | 1 | 0 | Duplicate PC 6.3 |

## How to Help

1. Pick a file from the list above
2. Compare the JSON against the original NOS PDF
3. Fix by either hand-editing (small fixes) or re-running extraction (bigger issues)
4. Run `python validate.py extracted_json/level-3/"<filename>"` to verify
5. Submit a PR with your fix

See [CONTRIBUTING.md](https://github.com/mdjibril/national-occupational-standard-framework/blob/main/CONTRIBUTING.md) for detailed instructions.

## Files That Passed ✅

Aluminium Cladding, Autobody Works (2 empty-description warnings), Fashion & Garment Making, Fish Farming, ICT CAD CAM, ICT Cinematography, ICT Computer Hardware, ICT Creative Media Production, ICT Social Media Communication, ICT Social Media Contents, ICT Web Development, Solar Photovoltaic

## Note on New Validation Rule

`validate.py` now flags learning outcomes with an empty `performance_criteria` array as an error (`EmptyPerformanceCriteriaRule`). This surfaced 5 additional errors in Agricultural Equipment Mechanics, Cosmetology, and Refrigeration & AC.

To reproduce: `python validate.py extracted_json/level-3/`
