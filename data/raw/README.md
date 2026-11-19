# Raw data

These files are public US government data. They are not committed because of their size; download them again with the links below.

| File | Source | Size | Notes |
|---|---|---|---|
| `January2015toNovember2025.zip` (holds `January2015toNovember2025.csv`) | OSHA Severe Injury Reports, "Download the full SIR data set" on https://www.osha.gov/severe-injury-reports | 16.2 MB zip, 57.4 MB CSV | 105,996 reports from 1 January 2015 to 30 November 2025, federal OSHA states only. The site blocks scripted downloads, so download it in a browser |
| `OSHA_violation.zip` | DOL Open Data Portal, OSHA Violation dataset: https://data.dol.gov/datasets/10338 ("Download Complete Dataset") | 2.28 GB | Every OSHA citation (13.3 million rows, 14 CSV chunks); no API key needed for the full download. Not kept on disk for now |

The SIR "Inspection" number (7 digits) is not the DOL `activity_nr` (9 digits since 2015), so the two files cannot be joined on it; see the warning in `scripts/join_sir_violations.py`.
