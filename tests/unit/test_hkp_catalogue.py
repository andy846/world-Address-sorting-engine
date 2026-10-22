import csv
import hashlib
import json
from pathlib import Path

import pytest
from world_address_engine.hkp.catalogue import import_hkp_catalogue, lookup_hkp_code

HEADERS = ("destination_id", "code_scheme", "code", "name_en", "name_zh_hant", "name_zh_hans",
           "source_url", "source_doc_version", "source_section", "source_checksum", "approval_status", "profile", "date_verified")
HKP_SOURCE = "https://ec-ship.hongkongpost.hk/platform/data/imailZoneChart_v2.pdf"


def sources(tmp_path: Path, rows: list[dict], *, checksum_mismatch=False):
    csv_path = tmp_path / "master.csv"
    with csv_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=HEADERS)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: row.get(key, "") for key in HEADERS})
    digest = hashlib.sha256(csv_path.read_bytes()).hexdigest()
    manifest = tmp_path / "master.manifest.json"
    manifest.write_text(json.dumps({"catalogue_version": "fixture-2026-10", "csv_sha256": "invalid" if checksum_mismatch else digest}), encoding="utf-8")
    return csv_path, manifest


def item(dest, scheme, code, status="APPROVED", profile="HKP_DESTINATION_2"):
    return dict(destination_id=dest, code_scheme=scheme, code=code, name_en=dest,
                name_zh_hant="", name_zh_hans="", source_url=HKP_SOURCE,
                source_doc_version="chart-v2", source_section="Destination & Zone Chart",
                source_checksum="source-reference-pending-full-master-audit", approval_status=status,
                profile=profile, date_verified="2026-10-23")


def test_hkp_tp_is_not_iso_tl(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("timor-leste", "HKP_DESTINATION_2", "TP"), item("timor-leste", "ISO_ALPHA2", "TL", profile="ISO")])
    db = tmp_path / "hkp.db"
    assert import_hkp_catalogue(csv_path, manifest, db) == 2
    assert lookup_hkp_code(db, "timor-leste") == "TP"
    assert lookup_hkp_code(db, "timor-leste", "ISO") is None


def test_fra_is_not_bulk_fr(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("france", "HKP_DESTINATION_2", "FR"), item("france", "ECSHIP_3", "FRA", profile="ECSHIP_INDIVIDUAL")])
    db = tmp_path / "hkp.db"
    import_hkp_catalogue(csv_path, manifest, db)
    assert lookup_hkp_code(db, "france") == "FR"
    assert lookup_hkp_code(db, "france", "ECSHIP_INDIVIDUAL") is None


def test_conflicting_approved_rows_are_rejected(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("timor-leste", "HKP_DESTINATION_2", "TP"), item("timor-leste", "HKP_DESTINATION_2", "TL")])
    with pytest.raises(ValueError, match="conflict"):
        import_hkp_catalogue(csv_path, manifest, tmp_path / "db.sqlite")
    assert not (tmp_path / "db.sqlite").exists()


def test_unapproved_mapping_returns_none(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("narnia", "HKP_DESTINATION_2", "NR", status="PENDING")])
    db = tmp_path / "db.sqlite"
    import_hkp_catalogue(csv_path, manifest, db)
    assert lookup_hkp_code(db, "narnia") is None


def test_wrong_manifest_hash_rejected(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("france", "HKP_DESTINATION_2", "FR")], checksum_mismatch=True)
    with pytest.raises(ValueError, match="checksum"):
        import_hkp_catalogue(csv_path, manifest, tmp_path / "db.sqlite")


def test_malformed_hkp_code_rejected(tmp_path):
    csv_path, manifest = sources(tmp_path, [item("france", "HKP_DESTINATION_2", "FRA")])
    with pytest.raises(ValueError, match="two uppercase"):
        import_hkp_catalogue(csv_path, manifest, tmp_path / "db.sqlite")


def test_unverified_source_url_rejected(tmp_path):
    row = item("france", "HKP_DESTINATION_2", "FR")
    row["source_url"] = "https://example.com/guess"
    csv_path, manifest = sources(tmp_path, [row])
    with pytest.raises(ValueError, match="Hongkong Post"):
        import_hkp_catalogue(csv_path, manifest, tmp_path / "db.sqlite")
