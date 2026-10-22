"""Verify the REAL worldwide GeoNames packs, not synthetic fixtures.

These tests run against the databases produced by the successful GitHub
Actions global build (run 39827512415, commit 929bbe6). They are skipped
unless the packs are present locally, because the artefacts are far too large
to commit to the repository.

Point WASE_REAL_PACK_DIR at the directory holding
`compact/compact_global.sqlite` and `extended/extended_global.sqlite`, or
leave it unset to use the default `builds/real-2026-10-22` location.
"""

import hashlib
import json
import os
from pathlib import Path
import zipfile

import pytest

from world_address_engine.data.pack_registry import install_pack, verify_pack
from world_address_engine.sqlite_util import open_db

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = Path(os.environ.get("WASE_REAL_PACK_DIR",
                                REPO_ROOT / "builds" / "real-2026-10-22"))

EXPECTED = {
    "COMPACT_GLOBAL": {
        "path": PACK_ROOT / "compact" / "compact_global.sqlite",
        "bytes": 143949824,
        "db_sha256": "e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d",
        "place_count": 715567,
        "alias_count": 997281,
        "compressed_bytes": 56535390,
    },
    "EXTENDED_GLOBAL": {
        "path": PACK_ROOT / "extended" / "extended_global.sqlite",
        "bytes": 1098661888,
        "db_sha256": "fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a",
        "place_count": 5776152,
        "alias_count": 8126852,
        "compressed_bytes": 423280495,
    },
}

ALLOWED_LANGUAGES = {"source-latin", "source-zh", "ascii", "en",
                      "zh", "zh-CN", "zh-TW", "zh-Hans", "zh-Hant"}


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def profile(name):
    expected = EXPECTED[name]
    if not expected["path"].is_file():
        pytest.skip(f"real {name} pack not present at {expected['path']}")
    return expected


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_matches_published_fingerprint(name):
    expected = profile(name)
    path = expected["path"]
    assert path.stat().st_size == expected["bytes"]
    assert sha256(path) == expected["db_sha256"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_passes_sqlite_integrity_check(name):
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_schema_and_counts_match_the_build_report(name):
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'")}
        assert {"geo_places", "geo_aliases", "pack_metadata"} <= tables
        indexes = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name NOT LIKE 'sqlite_%'")}
        assert {"idx_geo_alias_key", "idx_geo_country_admin"} <= indexes
        assert conn.execute("SELECT profile FROM pack_metadata").fetchone()[0] == name
        assert conn.execute("SELECT COUNT(*) FROM geo_places").fetchone()[0] == expected["place_count"]
        assert conn.execute("SELECT COUNT(*) FROM geo_aliases").fetchone()[0] == expected["alias_count"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_contains_only_admin_and_populated_features(name):
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        classes = {row[0] for row in conn.execute(
            "SELECT DISTINCT feature_class FROM geo_places")}
        assert classes <= {"A", "P"}
        languages = {row[0] for row in conn.execute(
            "SELECT DISTINCT language FROM geo_aliases")}
        assert languages <= ALLOWED_LANGUAGES


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_lookup_uses_an_index(name):
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT p.place_id FROM geo_aliases a "
            "JOIN geo_places p ON p.place_id=a.place_id WHERE a.search_key IN ('tokyo')"))
        assert "idx_geo_alias_key" in plan
        assert "SCAN" not in plan


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_resolves_distinct_postal_territories(name):
    """Macau, Hong Kong, Taiwan, Guam and Puerto Rico must stay separate places."""
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        def countries(term):
            return {row[0] for row in conn.execute(
                "SELECT DISTINCT p.country_code FROM geo_aliases a "
                "JOIN geo_places p ON p.place_id=a.place_id WHERE a.search_key=?", (term,))}
        assert "MO" in countries("macau")
        assert "HK" in countries("香港")
        assert "TW" in countries("taipei")
        assert "GU" in countries("guam")
        assert "PR" in countries("puerto rico")


def test_real_packs_install_offline_and_stay_queryable(tmp_path):
    """The whole point of the pack registry: verify, publish, then query."""
    expected = profile("COMPACT_GLOBAL")
    manifest = {
        "pack_id": "geonames-compact-global",
        "profile": "COMPACT_GLOBAL",
        "pack_version": "2026-10-22",
        "schema_version": 1,
        "created_at": "2026-10-22",
        "source_date": "2026-10-22",
        "source_sha256": "0" * 64,
        "db_sha256": expected["db_sha256"],
        "record_count": expected["place_count"],
        "alias_count_by_language": {"en": 59238},
        "attribution": "GeoNames (https://www.geonames.org/export/)",
        "license": "CC BY 4.0",
    }
    installed = install_pack(expected["path"], manifest, tmp_path / "packs")
    assert installed.name == "geonames-compact-global-2026-10-22"
    assert verify_pack(installed / "pack.db", installed / "manifest.json")
    with open_db(installed / "pack.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM geo_places").fetchone()[0] == expected["place_count"]
        assert conn.execute("SELECT COUNT(*) FROM geo_aliases").fetchone()[0] == expected["alias_count"]
        row = conn.execute(
            "SELECT p.country_code FROM geo_aliases a JOIN geo_places p ON p.place_id=a.place_id "
            "WHERE a.search_key='tokyo' LIMIT 1").fetchone()
        assert row[0] == "JP"


def test_real_build_report_matches_the_published_fingerprints():
    report_path = PACK_ROOT / "report" / "geonames-built" / "build_report.json"
    if not report_path.is_file():
        pytest.skip("build_report.json not present")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, expected in EXPECTED.items():
        built = report["profiles"][name]
        assert built["db_sha256"] == expected["db_sha256"]
        assert built["sqlite_bytes"] == expected["bytes"]
        assert built["place_count"] == expected["place_count"]
        assert built["alias_count"] == expected["alias_count"]
    assert report["sources"]["allCountries"]["sha256"] == (
        "4b8a10021d69736be2f78b75cbd6f49648f50bcd90da117cc1c4f84767725182")
    assert report["sources"]["alternateNamesV2"]["sha256"] == (
        "1ea8afef7da35370529cd2f7c38caac78e821ca3578f18f0207e5c31ee81fb05")
    assert report["sources"]["cities1000"]["sha256"] == (
        "9d3916f7a9448bb4ea45e93c06c5413d2cceb1a89e03f75c2178bbb08af12018")


def test_real_pack_zip_archives_hold_the_expected_database():
    for name, expected in EXPECTED.items():
        archive = PACK_ROOT / "packs" / (name.lower() + ".sqlite.zip")
        if not archive.is_file():
            pytest.skip(f"compressed archive not present for {name}")
        assert archive.stat().st_size == expected["compressed_bytes"]
        with zipfile.ZipFile(archive) as zf:
            members = [n for n in zf.namelist() if n.endswith(".sqlite")]
            assert members == [name.lower() + ".sqlite"]
