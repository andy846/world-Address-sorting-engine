"""Reproduce literal zone mappings from the original pinned country PDF.

Usage: python tools/import_country_zones.py SOURCE.pdf [--output PATH]
Requires pypdf only when importing; it is never a runtime dependency.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from world_address_engine.data.country_codes import SOURCE_FILENAME, SOURCE_SHA256, load_country_codes
from world_address_engine.data.zone_mappings import _load_bytes

# Reuse the unchanged parser for country identities, including wrapped names.
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))
from import_country_codes import parse_pages as parse_country_pages


def parse_pages(pages: list[str]) -> list[dict]:
    """Reconcile every row against the country catalogue, then read its tail.

    Zone is centered in the header: slicing at its header position truncates
    values. Instead split the country-code tail into code, middle zone tokens,
    and final NOVSN token. CNS stays an audit row, never an active CN mapping.
    """
    countries = load_country_codes()
    identities = parse_country_pages(pages)
    expected = [asdict(row) for row in countries.source_rows]
    if len(pages) != 5 or identities != expected:
        raise ValueError("source rows/order/pages/codes/names differ from the pinned country catalogue")
    rows = []
    for page_number, text in enumerate(pages, 1):
        lines = text.splitlines()
        header = next(line for line in lines if "Country NameE" in line and "SEQ" in line)
        code_start = header.index("Country", header.index("Country NameE") + len("Country NameE"))
        for line in lines[lines.index(header) + 1:]:
            match = re.match(r"^(\d+)\s", line)
            if match is None:
                continue
            cells = line[code_start:].split()
            identity = identities[len(rows)]
            if (len(cells) < 3 or cells[0] != identity["code"]
                    or int(match.group(1)) != identity["seq"] or page_number != identity["page"]):
                raise ValueError("missing or inconsistent country/Zone/NOVSN source cells")
            rows.append({**identity, "zone_code": " ".join(cells[1:-1]), "novsn_zone_code": cells[-1]})
    return rows


def _serialize(data: dict) -> bytes:
    return (json.dumps(data, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


def build_catalogue(pages: list[str]) -> dict:
    """Build and strictly validate all public table data before writing output."""
    rows = parse_pages(pages)
    data = {
        "schema_version": 1, "version": "user-provided-zones-20250708-v1", "profile": "USER_PROVIDED",
        "source": {"filename": SOURCE_FILENAME, "sha256": SOURCE_SHA256,
                   "page_count": len(pages), "row_count": len(rows)},
        "entries": [{"country_code": row["code"], "zone_code": row["zone_code"],
                     "novsn_zone_code": row["novsn_zone_code"]}
                    for row in rows if row["exclusion_reason"] is None],
        "source_rows": rows,
    }
    _load_bytes(_serialize(data))
    return data


def import_country_zones(pdf_path: Path, output_path: Path) -> dict:
    """Hash the original PDF and deterministically emit its verified mapping."""
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
                        default=ROOT / "src/world_address_engine/resources/country_zone_mappings.json")
    args = parser.parse_args()
    data = import_country_zones(args.pdf, args.output)
    print(f"Imported {len(data['source_rows'])} source rows; {len(data['entries'])} active zone mappings (USER_PROVIDED)")


if __name__ == "__main__":
    main()
