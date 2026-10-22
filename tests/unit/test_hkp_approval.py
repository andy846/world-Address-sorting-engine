"""Tests for the release-controlled approval of the HKP destination master.

The catalogue data file must never be able to assert its own production
approval. Authority lives in a signed manifest whose key is held outside
the repository, and the manifest binds the catalogue version, the source
CSV digest, the row count and the built database digest.
"""

import csv
import hashlib
import json
from pathlib import Path

import pytest

from world_address_engine.hkp.approval import (
    ApprovalError,
    SCOPE_PRODUCTION,
    SCOPE_TEST_FIXTURE,
    load_approval,
    load_key,
    sign_manifest,
)
from world_address_engine.hkp.catalogue import import_hkp_catalogue, lookup_hkp_code

HEADERS = (
    "destination_id", "code_scheme", "code", "name_en", "name_zh_hant",
    "name_zh_hans", "source_url", "source_doc_version", "source_section",
    "source_checksum", "approval_status", "profile", "date_verified",
)
SOURCE_URL = "https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf"
SOURCE_DOC = b"synthetic official document bytes for the fixture only"
SOURCE_SHA = hashlib.sha256(SOURCE_DOC).hexdigest()


def item(destination_id, code, *, scheme="HKP_DESTINATION_2", profile="HKP_DESTINATION_2",
         status="APPROVED", source_checksum=SOURCE_SHA):
    return dict(
        destination_id=destination_id, code_scheme=scheme, code=code,
        name_en=destination_id, name_zh_hant="", name_zh_hans="",
        source_url=SOURCE_URL, source_doc_version="chart-v2",
        source_section="Destination & Zone Chart", source_checksum=source_checksum,
        approval_status=status, profile=profile, date_verified="2026-10-23",
    )


def build_catalog(tmp_path: Path, rows):
    """Import a catalogue and return (csv_path, source_manifest_path, db_path)."""
    csv_path = tmp_path / "master.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=list(HEADERS))
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in HEADERS})
    source_manifest = tmp_path / "master.source.json"
    source_manifest.write_text(json.dumps({
        "catalogue_version": "fixture-2026-10",
        "csv_sha256": hashlib.sha256(csv_path.read_bytes()).hexdigest(),
    }), encoding="utf-8")
    db_path = tmp_path / "hkp.db"
    import_hkp_catalogue(csv_path, source_manifest, db_path)
    return csv_path, source_manifest, db_path


def approval_payload(db_path: Path, *, scope=SCOPE_TEST_FIXTURE,
                     approved_destinations=("france",), approved_sources=None,
                     csv_sha256=None, row_count=None, catalogue_version="fixture-2026-10"):
    payload = {
        "approval_id": "fixture-approval-1",
        "scope": scope,
        "catalogue_version": catalogue_version,
        "csv_sha256": csv_sha256 or "",
        "row_count": row_count if row_count is not None else 0,
        "catalogue_db_sha256": hashlib.sha256(Path(db_path).read_bytes()).hexdigest(),
        "approved_destinations": list(approved_destinations),
        "approved_sources": approved_sources if approved_sources is not None else [{
            "source_url": SOURCE_URL,
            "source_doc_version": "chart-v2",
            "source_section": "Destination & Zone Chart",
            "source_sha256": SOURCE_SHA,
        }],
    }
    return payload


def write_signed(tmp_path: Path, db_path: Path, key: bytes, *, csv_sha256=None,
                 row_count=None, **kwargs):
    payload = approval_payload(db_path, csv_sha256=csv_sha256, row_count=row_count, **kwargs)
    payload["csv_sha256"] = csv_sha256 or _db_csv_sha(db_path)
    payload["row_count"] = row_count if row_count is not None else _db_row_count(db_path)
    signed = sign_manifest(payload, key)
    manifest_path = tmp_path / "approval.json"
    manifest_path.write_text(json.dumps(signed, ensure_ascii=False, indent=2), encoding="utf-8")
    key_path = tmp_path / "approval.key"
    key_path.write_bytes(key)
    return manifest_path, key_path, signed


def _db_csv_sha(db_path: Path) -> str:
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT csv_sha256 FROM metadata").fetchone()[0]


def _db_row_count(db_path: Path) -> int:
    import sqlite3
    with sqlite3.connect(db_path) as conn:
        return conn.execute("SELECT COUNT(*) FROM destinations").fetchone()[0]


KEY = b"unit-test-approval-key-0123456789abcdef"


# --- signature and binding -----------------------------------------------------

def test_unsigned_manifest_is_rejected(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    payload = approval_payload(db)
    payload["csv_sha256"] = _db_csv_sha(db)
    payload["row_count"] = _db_row_count(db)
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps(payload), encoding="utf-8")
    key = tmp_path / "approval.key"
    key.write_bytes(KEY)
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)


def test_tampered_manifest_is_rejected(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    manifest, key, signed = write_signed(tmp_path, db, KEY)
    signed["approved_destinations"] = ["france", "china"]
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)


def test_wrong_key_is_rejected(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    manifest, key, _ = write_signed(tmp_path, db, KEY)
    other = tmp_path / "other.key"
    other.write_bytes(b"a-different-approval-key-0123456789abcd")
    with pytest.raises(ApprovalError):
        load_approval(manifest, other, db)


def test_manifest_must_bind_the_built_database_digest(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    payload = approval_payload(db)
    payload["csv_sha256"] = _db_csv_sha(db)
    payload["row_count"] = _db_row_count(db)
    payload["catalogue_db_sha256"] = "0" * 64
    signed = sign_manifest(payload, KEY)
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    key = tmp_path / "approval.key"
    key.write_bytes(KEY)
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)


def test_manifest_must_bind_the_catalogue_version_and_row_count(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    payload = approval_payload(db, catalogue_version="other-version")
    payload["csv_sha256"] = _db_csv_sha(db)
    payload["row_count"] = _db_row_count(db)
    signed = sign_manifest(payload, KEY)
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    key = tmp_path / "approval.key"
    key.write_bytes(KEY)
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)

    payload = approval_payload(db)
    payload["csv_sha256"] = _db_csv_sha(db)
    payload["row_count"] = _db_row_count(db) + 5
    signed = sign_manifest(payload, KEY)
    manifest.write_text(json.dumps(signed), encoding="utf-8")
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)


def test_approved_destination_absent_from_the_catalogue_is_rejected(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    manifest, key, _ = write_signed(tmp_path, db, KEY, approved_destinations=["france", "atlantis"])
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, db)


def test_short_key_is_rejected(tmp_path):
    key = tmp_path / "weak.key"
    key.write_bytes(b"short")
    with pytest.raises(ApprovalError):
        load_key(key)


def test_production_key_inside_the_repository_is_rejected(tmp_path):
    """A production approval key must live outside the source repository."""
    from world_address_engine.hkp import approval as module

    repository = module.repository_root()
    assert repository is not None, "the repository root must be discoverable"
    inside = repository / "tests" / "unit" / "approval.key"
    inside.write_bytes(KEY)
    try:
        with pytest.raises(ApprovalError):
            module.load_key(inside, scope=SCOPE_PRODUCTION)
    finally:
        inside.unlink(missing_ok=True)


def test_test_fixture_key_may_live_anywhere(tmp_path):
    key = tmp_path / "fixture.key"
    key.write_bytes(KEY)
    assert load_key(key, scope=SCOPE_TEST_FIXTURE) == KEY


# --- the audit probes ----------------------------------------------------------

def test_forged_database_cannot_assert_its_own_production_approval(tmp_path):
    """The exact P0-1 probe: a hand-made SQLite must not pass the gate."""
    import sqlite3

    forged = tmp_path / "forged.db"
    with sqlite3.connect(forged) as conn:
        conn.execute("CREATE TABLE metadata (catalogue_version TEXT, csv_sha256 TEXT, "
                     "row_count INTEGER, production_approved INTEGER)")
        conn.execute("INSERT INTO metadata VALUES ('forged', 'x', 1, 1)")
        conn.execute("""CREATE TABLE destinations (destination_id TEXT, code_scheme TEXT,
                         code TEXT, name_en TEXT, name_zh_hant TEXT, name_zh_hans TEXT,
                         source_url TEXT, source_doc_version TEXT, source_section TEXT,
                         source_checksum TEXT, approval_status TEXT, profile TEXT,
                         date_verified TEXT)""")
        conn.execute("""INSERT INTO destinations VALUES ('france','HKP_DESTINATION_2','ZZ',
                         'France','','','https://ec-ship.hongkongpost.hk/x.pdf','v','s',
                         'c','APPROVED','HKP_DESTINATION_2','2026-10-23')""")
    assert lookup_hkp_code(forged, "france") is None
    manifest = tmp_path / "approval.json"
    manifest.write_text(json.dumps({
        "approval_id": "forged", "scope": SCOPE_PRODUCTION,
        "catalogue_version": "forged", "csv_sha256": "x", "row_count": 1,
        "catalogue_db_sha256": hashlib.sha256(forged.read_bytes()).hexdigest(),
        "approved_destinations": ["france"], "approved_sources": [], "signature": "0" * 64,
    }), encoding="utf-8")
    key = tmp_path / "approval.key"
    key.write_bytes(KEY)
    with pytest.raises(ApprovalError):
        load_approval(manifest, key, forged)


def test_lookup_without_an_approval_never_returns_a_code(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    assert lookup_hkp_code(db, "france") is None


def test_csv_approval_status_alone_does_not_authorise_a_row(tmp_path):
    """P1-8: the signed manifest, not the CSV column, ratifies a row."""
    _, _, db = build_catalog(tmp_path, [item("france", "FR"), item("china", "CN")])
    manifest, key, _ = write_signed(tmp_path, db, KEY, approved_destinations=["france"])
    approval = load_approval(manifest, key, db)
    assert lookup_hkp_code(db, "france", approval=approval) == "FR"
    assert lookup_hkp_code(db, "china", approval=approval) is None


def test_provenance_must_match_a_signed_source_document(tmp_path):
    """A row whose source checksum is not a ratified document is not resolvable."""
    _, _, db = build_catalog(tmp_path, [item("france", "FR", source_checksum="b" * 64)])
    manifest, key, _ = write_signed(tmp_path, db, KEY)
    approval = load_approval(manifest, key, db)
    assert lookup_hkp_code(db, "france", approval=approval) is None


def test_verified_approval_resolves_the_code(tmp_path):
    _, _, db = build_catalog(tmp_path, [item("france", "FR")])
    manifest, key, _ = write_signed(tmp_path, db, KEY)
    approval = load_approval(manifest, key, db)
    assert approval.is_production is False
    assert lookup_hkp_code(db, "france", approval=approval) == "FR"
