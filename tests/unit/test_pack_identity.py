"""A pack must be published under the identity of the bytes it holds.

The build report is the evidence a pack is installed from, so it has to
state the snapshot date of the sources and the generation of the search
key format. When those fields are missing, guessing them publishes a
legacy database under the version of today's builder: two different
databases then claim one immutable version, and the legacy one silently
answers fewer questions than the reader asks.
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from build_reference_pack import (  # noqa: E402
    build,
    manifest_from_report,
    sqlite_writer_version,
    stamp_report_provenance,
)
from world_address_engine.data.geonames_builder import (  # noqa: E402
    LEGACY_PACK_FORMAT_VERSION,
    PACK_FORMAT_VERSION,
    pack_manifest,
)
from world_address_engine.data.pack_registry import (  # noqa: E402
    require_readable_pack,
)
from tests.unit.test_geonames_builder import make_sources  # noqa: E402


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "source"
    source.mkdir()
    make_sources(source)
    (source / "source_manifest.json").write_text(
        json.dumps({"source_date": "2026-10-23"}), encoding="utf-8")
    return source


def _legacy_pack(tmp_path: Path) -> Path:
    """A pack of the legacy generation: its keys keep the punctuation."""
    path = tmp_path / "legacy" / "pack.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE geo_aliases (search_key TEXT, place_id INTEGER)")
    conn.executemany("INSERT INTO geo_aliases VALUES (?, ?)",
                     [("st. john s", 1), ("tokyo", 2), ("香港", 3)])
    conn.commit()
    conn.close()
    return path


def _current_pack(tmp_path: Path) -> Path:
    """A pack of the current generation: its keys carry no punctuation."""
    path = tmp_path / "current" / "pack.db"
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE geo_aliases (search_key TEXT, place_id INTEGER)")
    conn.executemany("INSERT INTO geo_aliases VALUES (?, ?)",
                     [("st john s", 1), ("tokyo", 2), ("香港", 3)])
    conn.commit()
    conn.close()
    return path


def test_a_report_without_a_snapshot_date_is_refused(tmp_path):
    """The snapshot date cannot be guessed: it is part of the pack identity."""
    source = _source(tmp_path)
    report = build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)
    del report["source_date"]
    with pytest.raises(KeyError, match="source_date"):
        manifest_from_report(report, "COMPACT_GLOBAL")


def test_a_report_without_a_key_format_generation_is_refused(tmp_path):
    """A legacy report must never be published under today's generation."""
    source = _source(tmp_path)
    report = build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)
    del report["pack_format_version"]
    with pytest.raises(KeyError, match="pack_format_version"):
        manifest_from_report(report, "COMPACT_GLOBAL")


def test_the_generation_comes_from_the_report_and_not_from_the_builder(tmp_path,
                                                                      monkeypatch):
    """The manifest is a pure function of the report it was derived from."""
    source = _source(tmp_path)
    report = build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)
    report["pack_format_version"] = "k7"
    manifest = manifest_from_report(report, "COMPACT_GLOBAL")
    assert manifest["pack_format_version"] == "k7"
    assert manifest["pack_version"] == "2026-10-23-k7"
    # A later bump of the builder's constant must not relabel the manifest.
    monkeypatch.setattr("world_address_engine.data.geonames_builder."
                        "PACK_FORMAT_VERSION", "k9")
    assert manifest_from_report(report, "COMPACT_GLOBAL") == manifest


def test_the_build_records_the_generation_and_the_writer(tmp_path):
    source = _source(tmp_path)
    report = build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)
    assert report["pack_format_version"] == PACK_FORMAT_VERSION
    assert report["sqlite_version"]
    manifest = manifest_from_report(report, "COMPACT_GLOBAL")
    assert manifest["pack_format_version"] == PACK_FORMAT_VERSION
    assert manifest["sqlite_version"] == report["sqlite_version"]


def test_an_older_report_can_be_completed_from_the_database_it_describes(tmp_path):
    """A report written before the provenance existed is stamped, not guessed."""
    source = _source(tmp_path)
    report = build(source, tmp_path / "pack", ["COMPACT_GLOBAL"], compress=False)
    del report["pack_format_version"]
    database = tmp_path / "pack" / "compact_global.sqlite"
    stamped = stamp_report_provenance(report, database)
    assert stamped["pack_format_version"] == PACK_FORMAT_VERSION
    assert stamped["sqlite_version"] == sqlite_writer_version(database)
    assert manifest_from_report(stamped, "COMPACT_GLOBAL")["pack_format_version"] \
        == PACK_FORMAT_VERSION


def test_the_manifest_records_the_generation_of_its_keys():
    manifest = pack_manifest(
        "COMPACT_GLOBAL",
        {"place_count": 1, "alias_count": 1, "sqlite_bytes": 1,
         "alias_count_by_language": {"en": 1}},
        {"allCountries": {"sha256": "0" * 64}},
        "2026-10-23", "0" * 64)
    assert manifest["pack_format_version"] == PACK_FORMAT_VERSION
    assert manifest["pack_version"].endswith(PACK_FORMAT_VERSION)


def test_a_legacy_pack_is_refused_by_the_current_reader(tmp_path):
    """Its keys keep the punctuation, so every punctuated name would vanish."""
    pack = _legacy_pack(tmp_path)
    with pytest.raises(ValueError, match="legacy"):
        require_readable_pack(pack)


def test_a_current_pack_is_accepted(tmp_path):
    pack = _current_pack(tmp_path)
    assert require_readable_pack(pack) == PACK_FORMAT_VERSION


def test_a_manifest_that_declares_another_generation_is_refused(tmp_path):
    pack = _current_pack(tmp_path)
    (pack.parent / "manifest.json").write_text(json.dumps({
        "pack_format_version": LEGACY_PACK_FORMAT_VERSION}), encoding="utf-8")
    with pytest.raises(ValueError, match="search key format"):
        require_readable_pack(pack)


def test_a_pack_without_a_manifest_is_still_checked(tmp_path):
    """A pack with no manifest is checked by its keys, not waved through."""
    pack = _legacy_pack(tmp_path)
    assert not (pack.parent / "manifest.json").exists()
    with pytest.raises(ValueError, match="legacy"):
        require_readable_pack(pack)
