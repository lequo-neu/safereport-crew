"""Keep the OSHA violations cited in inspections that followed a severe injury report.

WARNING (checked on 19 November 2026): this direct join does not work. The SIR "Inspection"
numbers have 7 digits (837147 to 1877022), while every DOL violation issued since 2015 has a
9 digit activity_nr, so the only matches are coincidences with 1980s inspections. Linking the
two needs a record match on the establishment, address and date through the OSHA inspection
dataset instead; do not use this script's output.

Reads the Severe Injury Reports CSV and the DOL OSHA violation zip without unpacking the
zip to disk, keeps only violation rows whose inspection number (activity_nr) appears in the
SIR "Inspection" column, drops deleted citations, and writes them with a short summary.

Usage:
    python3 -I scripts/join_sir_violations.py SIR_CSV VIOLATION_ZIP OUT_DIR
"""

from __future__ import annotations

from collections import Counter
import csv
import io
import json
from pathlib import Path
import re
import sys
import zipfile


csv.field_size_limit(10_000_000)


def inspection_key(value: str) -> str:
    """Inspection numbers as plain digits, so "1143952", "1143952.0" and " 1143952" match."""
    value = (value or "").strip()
    match = re.match(r"^0*(\d+)(?:\.0+)?$", value)
    return match.group(1) if match else ""


def cfr_part(standard: str) -> str:
    """The CFR part and section of a cited standard: "19101030 G02 IIA" is 1910.1030."""
    code = (standard or "").strip().split(" ")[0]
    if len(code) >= 5 and code[:4].isdigit():
        part, section = code[:4], code[4:].lstrip("0")
        return f"{part}.{section}" if section else part
    return code


def main(sir_path: str, zip_path: str, out_dir: str) -> None:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)

    with open(sir_path, newline="", encoding="utf-8", errors="replace") as handle:
        sir = list(csv.DictReader(handle))
    by_inspection: dict[str, list[dict[str, str]]] = {}
    for row in sir:
        key = inspection_key(row.get("Inspection", ""))
        if key:
            by_inspection.setdefault(key, []).append(row)
    manufacturing = {
        k
        for k, rows in by_inspection.items()
        if any(r["Primary NAICS"].startswith(("31", "32", "33")) for r in rows)
    }

    with zipfile.ZipFile(zip_path) as archive:
        members = [m for m in archive.namelist() if m.lower().endswith(".csv")]
        kept, scanned, deleted = [], 0, 0
        header = None
        for member in members:
            with archive.open(member) as raw:
                reader = csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig", errors="replace", newline=""))
                # The chunks name their columns in capitals; the portal documents them in lower case.
                names = [n.strip().lower() for n in next(reader)]
                header = header or names
                for values in reader:
                    row = dict(zip(names, values, strict=False))  # a short last row keeps the columns it has
                    scanned += 1
                    key = inspection_key(row.get("activity_nr", ""))
                    if key not in by_inspection:
                        continue
                    if (row.get("delete_flag") or "").strip().upper() == "X":
                        deleted += 1
                        continue
                    kept.append(row)

    out_csv = out / "sir_violations.csv"
    with out_csv.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header)
        writer.writeheader()
        writer.writerows(kept)

    cited = {inspection_key(r["activity_nr"]) for r in kept}
    parts = Counter(cfr_part(r["standard"]) for r in kept)
    summary = {
        "zip_members": members,
        "violation_rows_scanned": scanned,
        "sir_reports": len(sir),
        "sir_reports_with_inspection": sum(len(v) for v in by_inspection.values()),
        "sir_inspections": len(by_inspection),
        "sir_inspections_with_a_citation": len(cited),
        "share_of_inspections_with_a_citation": round(len(cited) / len(by_inspection), 4)
        if by_inspection
        else 0,
        "manufacturing_inspections": len(manufacturing),
        "manufacturing_inspections_with_a_citation": len(cited & manufacturing),
        "sir_reports_linked_to_a_citation": sum(len(by_inspection[k]) for k in cited),
        "violations_kept": len(kept),
        "deleted_citations_dropped": deleted,
        "violations_per_cited_inspection": round(len(kept) / len(cited), 2) if cited else 0,
        "violation_types": Counter((r.get("viol_type") or "").strip() for r in kept).most_common(),
        "top_cfr_sections": parts.most_common(15),
        "distinct_cfr_sections": len(parts),
        "general_duty_or_other": sum(1 for r in kept if not (r.get("standard") or "")[:4].isdigit()),
        "initial_penalty_total": round(sum(float(r.get("initial_penalty") or 0) for r in kept), 2),
        "current_penalty_total": round(sum(float(r.get("current_penalty") or 0) for r in kept), 2),
        "header": header,
    }
    (out / "sir_violations_summary.json").write_text(json.dumps(summary, indent=2))
    print(json.dumps({k: v for k, v in summary.items() if k != "header"}, indent=2))


if __name__ == "__main__":
    if len(sys.argv) != 4:
        sys.exit(__doc__)
    main(*sys.argv[1:])
