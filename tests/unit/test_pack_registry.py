import hashlib
import json
from pathlib import Path

import pytest
from world_address_engine.data.pack_registry import (
    PACK_DB_NAME,
    PACK_MANIFEST_NAME,
    activate_pack,
    canonical_manifest,
    install_pack,
    stage_pack,
    verify_pack,
)


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


def manifest_fields(**overrides):
    fields = {
        "pack_id": "geonames-compact-global",
        "profile": "COMPACT_GLOBAL",
        "pack_version": "2026-10-22",
        "schema_version": 1,
        "created_at": "2026-10-22",
        "source_date": "2026-10-22",
        "source_sha256": "0" * 64,
        "db_sha256": "0" * 64,
        "record_count": 715567,
        "alias_count_by_language": {"en": 59238},
        "attribution": "GeoNames",
        "license": "CC BY 4.0",
    }
    fields.update(overrides)
    return fields


def test_canonical_manifest_bytes_are_order_independent():
    fields = manifest_fields()
    reversed_fields = dict(reversed(list(fields.items())))
    assert canonical_manifest(fields) == canonical_manifest(reversed_fields)
    assert canonical_manifest(fields).endswith("\n")


def test_stage_pack_lays_out_builder_output_as_installable_pack(tmp_path):
    """The published builder emits <profile>.sqlite; the installer needs pack.db."""
    built = tmp_path / "compact_global.sqlite"
    built.write_bytes(b"built global sqlite payload")
    digest = hashlib.sha256(built.read_bytes()).hexdigest()
    staged = stage_pack(built, manifest_fields(db_sha256=digest), tmp_path / "staged")
    assert (staged / PACK_DB_NAME).read_bytes() == b"built global sqlite payload"
    assert (staged / PACK_MANIFEST_NAME).exists()
    assert verify_pack(staged / PACK_DB_NAME, staged / PACK_MANIFEST_NAME)


def test_install_pack_publishes_versioned_immutable_pack(tmp_path):
    built = tmp_path / "compact_global.sqlite"
    built.write_bytes(b"built global sqlite payload")
    digest = hashlib.sha256(built.read_bytes()).hexdigest()
    installed = install_pack(built, manifest_fields(db_sha256=digest), tmp_path / "packs")
    assert installed.name == "geonames-compact-global-2026-10-22"
    assert (installed / PACK_DB_NAME).read_bytes() == b"built global sqlite payload"
    assert verify_pack(installed / PACK_DB_NAME, installed / PACK_MANIFEST_NAME)
    with pytest.raises(FileExistsError):
        install_pack(built, manifest_fields(db_sha256=digest), tmp_path / "packs")


def test_install_pack_refuses_tampered_builder_output(tmp_path):
    built = tmp_path / "compact_global.sqlite"
    built.write_bytes(b"built global sqlite payload")
    digest = hashlib.sha256(built.read_bytes()).hexdigest()
    built.write_bytes(b"tampered payload")
    with pytest.raises(ValueError, match="checksum"):
        install_pack(built, manifest_fields(db_sha256=digest), tmp_path / "packs")
    assert not list((tmp_path / "packs").glob("geonames-compact-global-*"))


def test_a_rebuilt_pack_installs_beside_the_published_one(tmp_path):
    """Two different databases of the same source date must coexist.

    The published 2026-10-22 pack and the rebuilt pack hold different
    bytes. The immutable install refuses to overwrite a version, so the
    rebuilt pack has to carry its own version or it can never be
    installed at all.
    """
    legacy = tmp_path / "legacy.sqlite"
    legacy.write_bytes(b"legacy punctuation bearing payload")
    rebuilt = tmp_path / "rebuilt.sqlite"
    rebuilt.write_bytes(b"rebuilt punctuation free payload")
    root = tmp_path / "packs"
    first = install_pack(legacy, manifest_fields(
        db_sha256=hashlib.sha256(legacy.read_bytes()).hexdigest()), root)
    second = install_pack(rebuilt, manifest_fields(
        pack_version="2026-10-22-k2",
        db_sha256=hashlib.sha256(rebuilt.read_bytes()).hexdigest()), root)
    assert first.name == "geonames-compact-global-2026-10-22"
    assert second.name == "geonames-compact-global-2026-10-22-k2"
    assert (second / PACK_DB_NAME).read_bytes() == b"rebuilt punctuation free payload"
