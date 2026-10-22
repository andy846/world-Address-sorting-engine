"""Load and resolve HKP codes without silently substituting ISO country codes.

An operator must review the complete sourced postal master before production.
Sample rows used in tests are not an authoritative/current national inventory.

The catalogue file is *data*, never authority. A code is resolvable only when
a separately signed approval manifest ratifies both the destination and the
official document the row was taken from.
"""

import csv
import hashlib
import json
import os
import re
import sqlite3
import tempfile
from pathlib import Path
from urllib.parse import urlsplit

from world_address_engine.hkp.approval import CatalogueApproval
from world_address_engine.sqlite_util import open_db

SCHEME = "HKP_DESTINATION_2"
REQUIRED_FIELDS = frozenset({
    "destination_id", "code_scheme", "code", "name_en", "name_zh_hant", "name_zh_hans",
    "source_url", "source_doc_version", "source_section", "source_checksum",
    "approval_status", "profile", "date_verified",
})


def _validate_row(row: dict[str, str]) -> None:
    if not row["destination_id"].strip():
        raise ValueError("empty destination_id")
    if not row["code_scheme"] or not row["profile"] or not row["source_doc_version"] or not row["source_section"] or not row["source_checksum"] or not row["date_verified"]:
        raise ValueError("missing required code provenance")
    if row["approval_status"] not in ("APPROVED", "PENDING", "RETIRED", "REJECTED"):
        raise ValueError("unknown approval_status")
    if row["code_scheme"] == SCHEME:
        if row["profile"] != SCHEME or not re.fullmatch(r"[A-Z]{2}", row["code"]):
            raise ValueError("HKP destination needs two uppercase letters and HKP_DESTINATION_2 profile")
    elif row["code_scheme"] == "ECSHIP_3":
        if row["profile"] != "ECSHIP_INDIVIDUAL" or not re.fullmatch(r"[A-Z]{3}", row["code"]):
            raise ValueError("ECShip code requires 3 uppercase letters and dedicated profile")
    elif row["code_scheme"] == "ISO_ALPHA2":
        if row["profile"] != "ISO" or not re.fullmatch(r"[A-Z]{2}", row["code"]):
            raise ValueError("ISO_ALPHA2 requires two uppercase letters and ISO profile")
    else:
        raise ValueError("unknown country-code scheme")
    if row["approval_status"] == "APPROVED" and row["code_scheme"] == SCHEME:
        url = urlsplit(row["source_url"])
        if url.scheme != "https" or (url.hostname not in {"hongkongpost.hk", "www.hongkongpost.hk", "ec-ship.hongkongpost.hk"}):
            raise ValueError("approved HKP entry needs Hongkong Post official HTTPS source")


def import_hkp_catalogue(source_csv: Path, manifest_json: Path, db_path: Path) -> int:
    """Validate a pinned CSV and atomically install the SQLite lookup DB.

    Does not grant APPROVED status or certify source correctness; approval
    status must have been assigned by an independent source-review workflow.
    """
    source_csv, manifest_json, db_path = map(Path, (source_csv, manifest_json, db_path))
    meta = json.loads(manifest_json.read_text(encoding="utf-8"))
    digest = hashlib.sha256(source_csv.read_bytes()).hexdigest()
    if digest != meta.get("csv_sha256"):
        raise ValueError("catalogue checksum mismatch")
    if not meta.get("catalogue_version"):
        raise ValueError("missing catalogue version")
    db_path.parent.mkdir(parents=True, exist_ok=True)
    fd, tempfile_name = tempfile.mkstemp(prefix=".hkp-", suffix=".db", dir=db_path.parent)
    os.close(fd)
    temporary_db = Path(tempfile_name)
    try:
        with open_db(temporary_db) as conn:
            conn.execute("""CREATE TABLE metadata (catalogue_version TEXT NOT NULL,
                             csv_sha256 TEXT NOT NULL, row_count INTEGER NOT NULL)""")
            conn.execute("""CREATE TABLE destinations (
                destination_id TEXT NOT NULL, code_scheme TEXT NOT NULL,
                code TEXT NOT NULL, name_en TEXT NOT NULL, name_zh_hant TEXT NOT NULL,
                name_zh_hans TEXT NOT NULL, source_url TEXT NOT NULL,
                source_doc_version TEXT NOT NULL, source_section TEXT NOT NULL,
                source_checksum TEXT NOT NULL, approval_status TEXT NOT NULL,
                profile TEXT NOT NULL, date_verified TEXT NOT NULL,
                PRIMARY KEY (destination_id, code_scheme, profile)
            )""")
            with source_csv.open("r", encoding="utf-8-sig", newline="") as f:
                reader = csv.DictReader(f)
                if not reader.fieldnames or not REQUIRED_FIELDS.issubset(reader.fieldnames):
                    raise ValueError("missing required catalogue fields")
                count = 0
                for row in reader:
                    _validate_row(row)
                    try:
                        conn.execute("""INSERT INTO destinations VALUES
                            (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                            tuple(row[field] for field in (
                                "destination_id", "code_scheme", "code", "name_en",
                                "name_zh_hant", "name_zh_hans", "source_url",
                                "source_doc_version", "source_section", "source_checksum",
                                "approval_status", "profile", "date_verified",
                            )))
                    except sqlite3.IntegrityError as exc:
                        raise ValueError("conflict or duplicate destination mapping") from exc
                    count += 1
            conn.execute(
                "INSERT INTO metadata VALUES (?, ?, ?)",
                (meta["catalogue_version"], digest, count),
            )
            conn.execute("CREATE INDEX destinations_by_scheme ON destinations (code_scheme, profile, approval_status)")
            conn.commit()
        os.replace(temporary_db, db_path)
        return count
    finally:
        temporary_db.unlink(missing_ok=True)


def lookup_hkp_code(db_path: Path, destination_id: str, profile: str = SCHEME,
                    approval: CatalogueApproval | None = None) -> str | None:
    """Never substitute a different code scheme, even if destination exists.

    Without a verified approval no code is ever returned: the catalogue file
    cannot approve itself.
    """
    if profile != SCHEME or approval is None:
        return None
    if not approval.allows(destination_id):
        return None
    with open_db(db_path) as conn:
        row = conn.execute(
            """SELECT code, source_url, source_doc_version, source_checksum
               FROM destinations WHERE destination_id=?
               AND code_scheme=? AND profile=? AND approval_status='APPROVED'""",
            (destination_id, SCHEME, profile),
        ).fetchone()
    if not row:
        return None
    code, source_url, source_doc_version, source_checksum = row
    if not re.fullmatch(r"[A-Z]{2}", code or ""):
        return None
    if not approval.ratifies_source(source_url=source_url or "",
                                    source_doc_version=source_doc_version or "",
                                    source_checksum=source_checksum or ""):
        return None
    return code


def approved_codes(db_path: Path, approval: CatalogueApproval | None = None) -> dict[str, str]:
    """Every destination the approval lets the engine assert, and its code."""
    with open_db(db_path) as conn:
        rows = conn.execute(
            """SELECT destination_id, code, source_url, source_doc_version, source_checksum
               FROM destinations WHERE code_scheme='HKP_DESTINATION_2'
               AND profile='HKP_DESTINATION_2' AND approval_status='APPROVED' """,
        ).fetchall()
    codes: dict[str, str] = {}
    for destination_id, code, source_url, source_doc_version, source_checksum in rows:
        if not re.fullmatch(r"[A-Z]{2}", code or ""):
            continue
        if approval is not None and not (
                approval.allows(destination_id)
                and approval.ratifies_source(source_url=source_url or "",
                                             source_doc_version=source_doc_version or "",
                                             source_checksum=source_checksum or "")):
            continue
        codes[destination_id] = code
    return codes


def approved_destinations(db_path: Path, approval: CatalogueApproval | None = None
                           ) -> dict[str, dict[str, str]]:
    """Every approved destination, keyed by its two-letter code.

    The manual quality-control panel asserts a *code*, so the lookup the
    operator sees is code first. The value carries the identity the export
    has to repeat, so a corrected row names the same destination the
    catalogue holds.
    """
    with open_db(db_path) as conn:
        rows = conn.execute(
            """SELECT destination_id, code, name_en, name_zh_hant,
                      source_url, source_doc_version, source_checksum
               FROM destinations WHERE code_scheme='HKP_DESTINATION_2'
               AND profile='HKP_DESTINATION_2' AND approval_status='APPROVED' """,
        ).fetchall()
    found: dict[str, dict[str, str]] = {}
    for destination_id, code, name_en, name_tc, source_url, doc_version, checksum in rows:
        if not re.fullmatch(r"[A-Z]{2}", code or ""):
            continue
        if approval is not None and not (
                approval.allows(destination_id)
                and approval.ratifies_source(source_url=source_url or "",
                                             source_doc_version=doc_version or "",
                                             source_checksum=checksum or "")):
            continue
        found[code] = {
            'destination_id': destination_id,
            'name_en': name_en or "",
            'name_tc': name_tc or "",
        }
    return found
