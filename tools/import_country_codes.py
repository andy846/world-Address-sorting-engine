"""Reproduce the country-only USER_PROVIDED catalogue from the pinned PDF.

Usage: python tools/import_country_codes.py SOURCE.pdf [--output PATH]
Requires pypdf only when importing. Zone and Novsn columns are never read.
"""

from __future__ import annotations

import argparse
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from world_address_engine.data.country_codes import (
    SOURCE_FILENAME, SOURCE_SHA256, _geo_mapping, _load_bytes,
)


# Reviewed name variants only. These do not create geographic country matches.
ALIASES = {
    "AS": ("American Samoa",),
    "BA": ("Bosnia-Herzegovina",),
    "BG": ("Bulgaria", "Republic of Bulgaria"),
    "BH": ("Bahrain", "Kingdom of Bahrain"),
    "BN": ("Brunei",),
    "CC": ("Cocos Islands", "Keeling Islands"),
    "CD": ("Democratic Republic of the Congo", "DR Congo", "Congo-Kinshasa", "DRC"),
    "CF": ("Central African Republic",),
    "CG": ("Republic of the Congo", "Congo-Brazzaville"),
    "CI": ("Cote d'Ivoire", "Ivory Coast", "Republic of Cote d'Ivoire"),
    "CN": ("China", "Mainland China", "China Mainland", "People's Republic of China", "PRC",
           "\u4e2d\u570b", "\u4e2d\u570b\u5167\u5730"),
    "CV": ("Cabo Verde",),
    "CZ": ("Czech Republic", "Czechia"),
    "FK": ("Falkland Islands", "South Georgia and South Sandwich Islands"),
    "FM": ("Micronesia", "Federated States of Micronesia"),
    "GB": ("UK", "U.K.", "Great Britain", "United Kingdom of Great Britain and Northern Ireland"),
    "GP": ("Guadeloupe",),
    "HK": ("Hongkong",),
    "HN": ("Honduras", "Republic of Honduras"),
    "KN": ("Saint Kitts and Nevis", "St Kitts and Nevis", "Saint Christopher and Nevis"),
    "KP": ("North Korea", "Democratic People's Republic of Korea", "DPRK"),
    "KR": ("South Korea", "Republic of Korea"),
    "LA": ("Laos", "Lao People's Democratic Republic", "Lao PDR"),
    "LC": ("Saint Lucia", "St Lucia"),
    "MD": ("Republic of Moldova",),
    "MK": ("North Macedonia", "Republic of North Macedonia"),
    "MM": ("Burma",),
    "MO": ("Macao",),
    "MP": ("Northern Mariana Islands",),
    "MQ": ("Martinique",),
    "PA": ("Panama", "Republic of Panama"),
    "PM": ("Saint Pierre and Miquelon", "St Pierre and Miquelon"),
    "RE": ("Reunion",),
    "RU": ("Russia", "Russian Federation"),
    "RW": ("Rwanda", "Republic of Rwanda"),
    "SH": ("Saint Helena", "St Helena"),
    "SJ": ("Svalbard", "Spitsbergen"),
    "SZ": ("Swaziland",),
    "TP": ("Timor-Leste", "East Timor", "Democratic Republic of Timor-Leste"),
    "TR": ("Turkiye", "T\u00fcrkiye"),
    "TZ": ("Tanzania", "United Republic of Tanzania"),
    "US": ("United States", "USA", "U.S.A.", "US", "U.S."),
    "VA": ("Vatican City", "Holy See"),
    "VC": ("Saint Vincent and the Grenadines", "St Vincent and the Grenadines"),
    "VE": ("Venezuela", "Bolivarian Republic of Venezuela"),
    "VG": ("British Virgin Islands", "Tortola"),
    "VI": ("US Virgin Islands", "U.S. Virgin Islands", "United States Virgin Islands"),
    "VN": ("Vietnam",),
    "WS": ("Samoa", "Independent State of Samoa"),
    "XD": ("Ascension Island",),
}


def parse_pages(pages: list[str]) -> list[dict]:
    """Extract only source sequence, country names, country code and page.

    Layout text aligns characters to the page's own header. Continuation lines
    append Chinese without a space and English with a space, retaining row 73.
    """
    rows = []
    for page_number, text in enumerate(pages, 1):
        lines = text.splitlines()
        header = next((line for line in lines if "Country NameE" in line and "SEQ" in line), None)
        if header is None:
            raise ValueError(f"missing country table header on page {page_number}")
        tc_start = header.index("Country NameC")
        en_start = header.index("Country NameE")
        code_start = header.index("Country", en_start + len("Country NameE"))
        current = None
        for line in lines[lines.index(header) + 1:]:
            if not line.strip() or re.fullmatch(r"\s*\d+/\d+\s*", line):
                continue
            match = re.match(r"^(\d+)\s", line)
            if match:
                code_cells = line[code_start:].split()
                if not code_cells:
                    raise ValueError("missing Country Code in source row")
                code = code_cells[0]
                current = {
                    "seq": int(match.group(1)), "page": page_number,
                    "code": code, "name_tc": line[tc_start:en_start].strip(),
                    "name_en": line[en_start:code_start].strip(),
                    "canonical_code": "CN" if code == "CNS" else code,
                    "exclusion_reason": "service_duplicate" if code == "CNS" else None,
                }
                rows.append(current)
            elif current is not None:
                tc = line[tc_start:en_start].strip()
                en = line[en_start:code_start].strip()
                if line[:tc_start].strip() or line[code_start:].strip() or not (tc or en):
                    raise ValueError(f"unrecognized continuation on page {page_number}")
                current["name_tc"] += tc
                if en:
                    current["name_en"] += " " + en
    return rows


def build_catalogue(pages: list[str]) -> dict:
    """Build and validate the complete schema before any output is written."""
    rows = parse_pages(pages)
    entries = []
    for row in rows:
        if row["exclusion_reason"] is not None:
            continue
        code = row["code"]
        aliases = [row["name_en"], row["name_tc"], row["name_en"].title(), *ALIASES.get(code, ())]
        entries.append({"code": code, "name_en": row["name_en"], "name_tc": row["name_tc"],
                        "aliases": list(dict.fromkeys(aliases))})
    data = {
        "schema_version": 1, "version": "user-provided-20250708-v1", "profile": "USER_PROVIDED",
        "source": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256,
                   "page_count": len(pages), "row_count": len(rows)},
        "entries": entries, "source_rows": rows,
        "geo_to_code": _geo_mapping(entry["code"] for entry in entries),
    }
    _load_bytes(_serialize(data))
    return data


def _serialize(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def import_country_codes(pdf_path: Path, output_path: Path) -> dict:
    """Check the exact PDF, then deterministically emit the country catalogue."""
    raw = Path(pdf_path).read_bytes()
    if hashlib.sha256(raw).hexdigest() != SOURCE_SHA256:
        raise ValueError("source PDF SHA256 mismatch")
    from pypdf import PdfReader

    reader = PdfReader(BytesIO(raw))
    if len(reader.pages) != 5:
        raise ValueError("source PDF must contain exactly 5 pages")
    data = build_catalogue([page.extract_text(extraction_mode="layout") for page in reader.pages])
    output_path = Path(output_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_bytes(_serialize(data))
    return data


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--output", type=Path,
                        default=ROOT / "src/world_address_engine/resources/country_codes.json")
    args = parser.parse_args()
    data = import_country_codes(args.pdf, args.output)
    print(f"Imported {len(data['source_rows'])} source rows; {len(data['entries'])} canonical entries (USER_PROVIDED)")


if __name__ == "__main__":
    main()
