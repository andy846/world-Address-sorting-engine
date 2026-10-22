import hashlib
import json
from pathlib import Path

import pytest
from world_address_engine.data.pack_registry import activate_pack, verify_pack


def pack(tmp_path):
    staged = tmp_path / "staged"
    staged.mkdir()
    payload = staged / "pack.db"
    payload.write_bytes(b"small synthetic reference DB")
    digest = hashlib.sha256(payload.read_bytes()).hexdigest()
    manifest = staged / "manifest.json"
    manifest.write_text(json.dumps({
        "pack_id": "geonames", "profile": "COMPACT_GLOBAL", "pack_version": "fixture1",
        "schema_version": 1, "created_at": "2026-10-23", "source_date": "2026-10-01",
        "source_sha256": "0"*64, "db_sha256": digest, "record_count": 3,
        "alias_count_by_language": {"en": 3}, "attribution": "GeoNames", "license": "CC BY 4.0",
    }), encoding="utf-8")
    return staged, payload, manifest


def test_tampered_db_rejected(tmp_path):
    _, payload, manifest = pack(tmp_path)
    assert verify_pack(payload, manifest)
    payload.write_bytes(b"tampered")
    with pytest.raises(ValueError, match="checksum"):
        verify_pack(payload, manifest)


def test_partial_install_never_becomes_active(tmp_path):
    staged, payload, manifest = pack(tmp_path)
    manifest.unlink()
    with pytest.raises(FileNotFoundError):
        activate_pack(staged, tmp_path / "packs")
    assert not (tmp_path / "packs" / "geonames-fixture1").exists()


def test_manifest_fingerprints_fix_run_sources(tmp_path):
    staged, payload, manifest = pack(tmp_path)
    installed = activate_pack(staged, tmp_path / "packs")
    assert installed.name == "geonames-fixture1"
    assert verify_pack(installed / "pack.db", installed / "manifest.json")
    with pytest.raises(FileExistsError):
        activate_pack(installed, tmp_path / "packs")
