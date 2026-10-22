"""The GeoNames builder output must be installable as a versioned pack.

The published builder writes `<profile>.sqlite` plus `build_report.json`, but
`pack_registry` installs a directory holding `pack.db` and `manifest.json`.
These tests pin the manifest contract that bridges the two.
"""

from world_address_engine.data.geonames_builder import build_geonames_pack, pack_manifest
from world_address_engine.data.pack_registry import REQUIRED


METRICS = {
    "place_count": 715567,
    "alias_count": 997281,
    "sqlite_bytes": 143949824,
    "alias_count_by_language": {"en": 59238, "zh": 105713},
}

ARCHIVES = {
    "allCountries.zip": {
        "url": "https://download.geonames.org/export/dump/allCountries.zip",
        "bytes": 422156786,
        "sha256": "a" * 64,
    }
}


def test_pack_manifest_is_registry_compatible():
    manifest = pack_manifest("COMPACT_GLOBAL", METRICS, ARCHIVES, "2026-10-22", "b" * 64)
    assert REQUIRED <= manifest.keys()
    assert manifest["pack_id"] == "geonames-compact-global"
    assert manifest["profile"] == "COMPACT_GLOBAL"
    assert manifest["pack_version"] == "2026-10-22"
    assert manifest["record_count"] == 715567
    assert manifest["alias_count_by_language"] == METRICS["alias_count_by_language"]
    assert manifest["source_archives"] == ARCHIVES
    assert len(manifest["source_sha256"]) == 64
    assert len(manifest["db_sha256"]) == 64


def test_pack_manifest_is_byte_identical_for_the_same_source():
    first = pack_manifest("COMPACT_GLOBAL", METRICS, ARCHIVES, "2026-10-22", "b" * 64)
    second = pack_manifest("COMPACT_GLOBAL", dict(METRICS), dict(ARCHIVES), "2026-10-22", "b" * 64)
    assert first == second


def test_pack_manifest_source_hash_tracks_every_source_archive():
    changed = {"allCountries.zip": {"url": "u", "bytes": 1, "sha256": "c" * 64}}
    first = pack_manifest("COMPACT_GLOBAL", METRICS, ARCHIVES, "2026-10-22", "b" * 64)
    second = pack_manifest("COMPACT_GLOBAL", METRICS, changed, "2026-10-22", "b" * 64)
    assert first["source_sha256"] != second["source_sha256"]


def test_builder_reports_alias_counts_by_language(tmp_path):
    from tests.unit.test_geonames_builder import make_sources

    make_sources(tmp_path)
    stats = build_geonames_pack(tmp_path, tmp_path / "geo.db", "EXTENDED_GLOBAL")
    languages = stats["alias_count_by_language"]
    assert sum(languages.values()) == stats["alias_count"]


def test_alias_language_labels_are_not_double_counted(tmp_path):
    """One place/text pair is indexed once, so labels must sum to the alias count."""
    from tests.unit.test_geonames_builder import make_sources

    make_sources(tmp_path)
    stats = build_geonames_pack(tmp_path, tmp_path / "geo.db", "EXTENDED_GLOBAL")
    languages = stats["alias_count_by_language"]
    assert languages.get("source-latin", 0) >= 1
    assert sum(v for k, v in languages.items() if k.startswith("zh")) >= 1
    assert "ru" not in languages
    assert "ja" not in languages
