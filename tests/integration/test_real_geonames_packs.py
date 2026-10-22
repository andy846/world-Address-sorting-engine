"""Verify the REAL worldwide GeoNames packs, not synthetic fixtures.

These tests run against the real databases. They are skipped unless the
packs are present locally, because the artefacts are far too large to
commit to the repository.

Point WASE_REAL_PACK_DIR at the directory holding
`compact/compact_global.sqlite` and `extended/extended_global.sqlite`, or
leave it unset to use the default `builds/real-2026-10-22` location.

Point WASE_INSTALLED_PACK_DIR at the directory holding the installed
`geonames-<profile>-<version>` pack directories, or leave it unset to use
the default `packs` location.

Point WASE_PACK_GENERATION at the pack generation to verify: `2026-10-22`
is the published generation that carries the legacy, punctuation bearing
keys; `2026-10-22-k2` is the rebuilt generation that stores punctuation
free keys. The two hold different bytes and must both stay verifiable.

`PRAGMA integrity_check` over the 1 GiB EXTENDED_GLOBAL pack takes about a
minute, so that one check is opt-in: set WASE_SLOW_CHECKS=1 to run it.
"""

import hashlib
import json
import os
from pathlib import Path
import shutil
import zipfile

import pytest

from world_address_engine.data.pack_registry import (
    activate_pack,
    install_pack,
    verify_pack,
)
from world_address_engine.matching.retrieve import retrieve_candidates
from world_address_engine.sqlite_util import open_db

REPO_ROOT = Path(__file__).resolve().parents[2]

# Every published pack generation: where its databases live, where its
# installed copies live and the exact fingerprints of its bytes.
GENERATIONS = {
    "2026-10-22": {
        "root": REPO_ROOT / "builds" / "real-2026-10-22",
        "built": {"COMPACT_GLOBAL": "compact/compact_global.sqlite",
                  "EXTENDED_GLOBAL": "extended/extended_global.sqlite"},
        "installed": {"COMPACT_GLOBAL": "geonames-compact-global-2026-10-22",
                      "EXTENDED_GLOBAL": "geonames-extended-global-2026-10-22"},
        "report": "report/geonames-built/build_report.json",
        "zips": "packs",
        "profiles": {
            "COMPACT_GLOBAL": {
                "bytes": 143949824,
                "db_sha256": "e3b8b710e7acf05e0fe3618abecc5745d13d07a7826ae1f2a41767561faa2d2d",
                "place_count": 715567,
                "alias_count": 997281,
                "compressed_bytes": 56535390,
            },
            "EXTENDED_GLOBAL": {
                "bytes": 1098661888,
                "db_sha256": "fb0e4774cc360ec5fe7b22d2b8176feea031abf02a6277dc42a3877c9da2074a",
                "place_count": 5776152,
                "alias_count": 8126852,
                "compressed_bytes": 423280495,
            },
        },
    },
    # Rebuilt from the same pinned upstream archives with the punctuation
    # free key format. Fewer aliases, because names that differ only by
    # punctuation now share one key.
    "2026-10-22-k2": {
        "root": REPO_ROOT / "builds" / "real-2026-10-23",
        "built": {"COMPACT_GLOBAL": "pack/compact_global.sqlite",
                  "EXTENDED_GLOBAL": "pack/extended_global.sqlite"},
        "installed": {"COMPACT_GLOBAL": "geonames-compact-global-2026-10-22-k2",
                      "EXTENDED_GLOBAL": "geonames-extended-global-2026-10-22-k2"},
        "report": "pack/build_report.json",
        "zips": "pack",
        "profiles": {
            "COMPACT_GLOBAL": {
                "bytes": 142577664,
                "db_sha256": "f4ef044e94aa3d206f8fce1fa3e0d7ab5f03d6081d142fd7f9e8cf5837ab1b3f",
                "place_count": 715567,
                "alias_count": 993537,
                "compressed_bytes": 56480487,
            },
            "EXTENDED_GLOBAL": {
                "bytes": 1087344640,
                "db_sha256": "70d617a532b8faedd7d9703c9b952945f101334907df5936725123d20be1f70f",
                "place_count": 5776152,
                "alias_count": 8048422,
                "compressed_bytes": 420832046,
            },
        },
    },
}

GENERATION = os.environ.get("WASE_PACK_GENERATION", "2026-10-22").strip()
if GENERATION not in GENERATIONS:
    raise SystemExit(f"unknown pack generation {GENERATION!r}; "
                     f"choose one of {sorted(GENERATIONS)}")
LAYOUT = GENERATIONS[GENERATION]

PACK_ROOT = Path(os.environ.get("WASE_REAL_PACK_DIR", LAYOUT["root"]))

# The installed, versioned packs carry their own manifest next to pack.db.
INSTALLED_ROOT = Path(os.environ.get("WASE_INSTALLED_PACK_DIR",
                                     REPO_ROOT / "packs"))
INSTALLED_PACKS = {
    name: INSTALLED_ROOT / LAYOUT["installed"][name] for name in LAYOUT["profiles"]
}

# `PRAGMA integrity_check` over the 1 GiB EXTENDED_GLOBAL pack takes about a
# minute, so it is opt-in. Set WASE_SLOW_CHECKS=1 to run it.
SLOW_CHECKS = os.environ.get("WASE_SLOW_CHECKS", "").strip().lower() not in (
    "", "0", "false", "no")

# Upstream GeoNames archives pinned by the published build.
PUBLISHED_SOURCE_ARCHIVES = {
    "allCountries":
        "4b8a10021d69736be2f78b75cbd6f49648f50bcd90da117cc1c4f84767725182",
    "alternateNamesV2":
        "1ea8afef7da35370529cd2f7c38caac78e821ca3578f18f0207e5c31ee81fb05",
    "cities1000":
        "9d3916f7a9448bb4ea45e93c06c5413d2cceb1a89e03f75c2178bbb08af12018",
}
PUBLISHED_SOURCE_SHA256 = (
    "568d05072b72ba2903804fce54a548a1d591a7302bc470db97a2fde1890e2629")

# The pack builder only indexes a place when its name is Latin script, or its
# country is CN/HK/MO/TW and its name is Han script, or its asciiname is
# Latin script. One EXTENDED_GLOBAL place (a Persian place whose name and
# asciiname are both non-Latin) therefore carries no alias row at all.
KNOWN_UNINDEXED_PLACES = {"COMPACT_GLOBAL": 0, "EXTENDED_GLOBAL": 1}

EXPECTED = {
    name: {"path": PACK_ROOT / LAYOUT["built"][name], **fingerprint}
    for name, fingerprint in LAYOUT["profiles"].items()
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


def installed_pack(name):
    """Return the installed pack directory, or skip when it is absent."""
    directory = INSTALLED_PACKS[name]
    if not (directory / "pack.db").is_file():
        pytest.skip(f"installed {name} pack not present at {directory}")
    if not (directory / "manifest.json").is_file():
        pytest.skip(f"installed {name} manifest not present at {directory}")
    return directory


def installed_manifest(name):
    """Return the manifest of the installed pack, or skip when it is absent."""
    path = installed_pack(name) / "manifest.json"
    return json.loads(path.read_text(encoding="utf-8"))


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_matches_published_fingerprint(name):
    expected = profile(name)
    path = expected["path"]
    assert path.stat().st_size == expected["bytes"]
    assert sha256(path) == expected["db_sha256"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_passes_sqlite_integrity_check(name):
    expected = profile(name)
    if name == "EXTENDED_GLOBAL" and not SLOW_CHECKS:
        pytest.skip(
            "PRAGMA integrity_check over the 1 GiB EXTENDED_GLOBAL pack takes "
            "about a minute; set WASE_SLOW_CHECKS=1 to run it")
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
        "pack_version": GENERATION,
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
    assert installed.name == f"geonames-compact-global-{GENERATION}"
    assert verify_pack(installed / "pack.db", installed / "manifest.json")
    with open_db(installed / "pack.db") as conn:
        assert conn.execute("SELECT COUNT(*) FROM geo_places").fetchone()[0] == expected["place_count"]
        assert conn.execute("SELECT COUNT(*) FROM geo_aliases").fetchone()[0] == expected["alias_count"]
        row = conn.execute(
            "SELECT p.country_code FROM geo_aliases a JOIN geo_places p ON p.place_id=a.place_id "
            "WHERE a.search_key='tokyo' LIMIT 1").fetchone()
        assert row[0] == "JP"


def test_real_build_report_matches_the_published_fingerprints():
    report_path = PACK_ROOT / LAYOUT["report"]
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
        archive = PACK_ROOT / LAYOUT["zips"] / (name.lower() + ".sqlite.zip")
        if not archive.is_file():
            pytest.skip(f"compressed archive not present for {name}")
        assert archive.stat().st_size == expected["compressed_bytes"]
        with zipfile.ZipFile(archive) as zf:
            members = [n for n in zf.namelist() if n.endswith(".sqlite")]
            assert members == [name.lower() + ".sqlite"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_installed_pack_matches_the_published_fingerprint(name):
    """The installed pack.db is byte identical to the published artefact."""
    directory = installed_pack(name)
    expected = EXPECTED[name]
    manifest = installed_manifest(name)
    pack_db = directory / "pack.db"
    assert pack_db.stat().st_size == expected["bytes"]
    assert sha256(pack_db) == expected["db_sha256"]
    assert manifest["db_sha256"] == expected["db_sha256"]
    assert manifest["record_count"] == expected["place_count"]
    assert manifest["alias_count"] == expected["alias_count"]
    assert manifest["profile"] == name
    assert manifest["pack_version"] == GENERATION
    assert manifest["schema_version"] == 1


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_installed_pack_manifest_pins_the_published_source_archives(name):
    """The manifest names the exact upstream archives the pack was built from."""
    installed_pack(name)
    manifest = installed_manifest(name)
    archives = manifest["source_archives"]
    for source, digest in PUBLISHED_SOURCE_ARCHIVES.items():
        assert archives[source]["sha256"] == digest
    assert manifest["source_sha256"] == PUBLISHED_SOURCE_SHA256
    assert manifest["source_date"] == "2026-10-22"
    assert manifest["created_at"] == "2026-10-22"
    assert manifest["attribution"] == "GeoNames (https://www.geonames.org/export/)"
    assert manifest["license"] == "CC BY 4.0"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_alias_language_breakdown_matches_the_manifest(name):
    """Every alias language bucket matches the manifest, Latin and Chinese alike."""
    expected = profile(name)
    manifest = installed_manifest(name)
    with open_db(expected["path"]) as conn:
        breakdown = dict(conn.execute(
            "SELECT language, COUNT(*) FROM geo_aliases GROUP BY language"))
        assert breakdown == manifest["alias_count_by_language"]
        assert sum(breakdown.values()) == manifest["alias_count"]
        assert manifest["alias_count"] == expected["alias_count"]
        latin = sum(breakdown.get(tag, 0)
                    for tag in ("source-latin", "ascii", "en"))
        chinese = sum(breakdown.get(tag, 0)
                      for tag in ("source-zh", "zh", "zh-CN", "zh-TW",
                                  "zh-Hans", "zh-Hant"))
        assert latin + chinese == manifest["alias_count"]
        assert latin > 0, "no Latin or English alias is indexed"
        assert chinese > 0, "no Chinese alias is indexed"


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_geography_hierarchy_is_populated(name):
    """Countries, admin1 and admin2 are real dimensions of the gazetteer."""
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        countries = conn.execute(
            "SELECT COUNT(DISTINCT country_code) FROM geo_places").fetchone()[0]
        admin1 = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT country_code, admin1_code "
            "FROM geo_places)").fetchone()[0]
        admin2 = conn.execute(
            "SELECT COUNT(*) FROM (SELECT DISTINCT country_code, admin1_code, "
            "admin2_code FROM geo_places)").fetchone()[0]
        assert countries == 253
        assert admin1 >= countries
        assert admin2 >= admin1
        assert admin2 <= expected["place_count"]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_hierarchy_lookup_uses_the_country_admin_index(name):
    """The country/admin index answers the hierarchy lookups, not a table scan."""
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        plan = " ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT place_id, name FROM geo_places "
            "WHERE country_code=? AND admin1_code=? AND admin2_code=?",
            ("HK", "00", "00")))
        assert "idx_geo_country_admin" in plan
        assert "SCAN" not in plan


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_multi_key_join_uses_the_alias_index(name):
    """The batched join the reader issues stays on the alias index."""
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        plan = " | ".join(row[3] for row in conn.execute(
            "EXPLAIN QUERY PLAN SELECT p.place_id, p.name FROM geo_aliases a "
            "JOIN geo_places p ON p.place_id=a.place_id WHERE a.search_key IN "
            "('tokyo','mumbai','hong kong','香港','臺北市','廣州市')"))
        assert "idx_geo_alias_key" in plan
        assert "SEARCH a" in plan
        assert "SCAN a" not in plan
        assert "SEARCH p USING INTEGER PRIMARY KEY" in plan


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_resolves_real_world_cities(name):
    """Latin, Traditional Chinese and Simplified Chinese forms all resolve."""
    expected = profile(name)
    cases = {
        "Tokyo": "JP",
        "Mumbai": "IN",
        "Hong Kong": "HK",
        "香港": "HK",
        "澳門": "MO",
        "廣州市": "CN",
        "广州市": "CN",
        "臺北市": "TW",
        "台北市": "TW",
        "São Paulo": "BR",
    }
    for form, country in cases.items():
        candidates = retrieve_candidates(expected["path"], (form,), limit=10)
        assert candidates, f"{form!r} produced no candidate"
        found = {c.destination_id: c.support for c in candidates}
        assert country in found, f"{form!r} did not resolve to {country}"
        assert found[country] == max(found.values()), (
            f"{form!r} ranked {country} below {found}")


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_reaches_a_punctuation_bearing_name(name):
    """A name with punctuation must resolve in both key generations.

    The published generation stores the punctuation in the key; the
    rebuilt generation folds it away and the reader folds it away with it.
    Either way the place has to be found.
    """
    expected = profile(name)
    candidates = retrieve_candidates(expected["path"], ("St. Louis",), limit=10)
    assert any(c.destination_id == "US" for c in candidates)


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_aliases_all_point_at_a_real_place(name):
    """Only the known unindexed place has no alias row."""
    expected = profile(name)
    with open_db(expected["path"]) as conn:
        unindexed = conn.execute(
            "SELECT COUNT(*) FROM geo_places WHERE place_id NOT IN "
            "(SELECT place_id FROM geo_aliases)"
        ).fetchone()[0]
        assert unindexed == KNOWN_UNINDEXED_PLACES[name]


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_real_pack_has_no_dangling_alias(name):
    """Every alias row points at a place that exists."""
    expected = profile(name)
    if not SLOW_CHECKS:
        pytest.skip(
            "the exact dangling-alias sweep reads every alias row; set "
            "WASE_SLOW_CHECKS=1 to run it")
    with open_db(expected["path"]) as conn:
        dangling = conn.execute(
            "SELECT COUNT(*) FROM geo_aliases a WHERE NOT EXISTS "
            "(SELECT 1 FROM geo_places p WHERE p.place_id=a.place_id)"
        ).fetchone()[0]
        assert dangling == 0


@pytest.mark.parametrize("name", sorted(EXPECTED))
def test_installed_pack_verifies_activates_and_refuses_tampering(name, tmp_path):
    """verify_pack, activate_pack and the immutable-pack guard, offline."""
    directory = installed_pack(name)
    expected = EXPECTED[name]
    assert verify_pack(directory / "pack.db", directory / "manifest.json")

    active_root = tmp_path / "active"
    installed = activate_pack(directory, active_root)
    assert installed.name == directory.name
    assert (installed / "pack.db").stat().st_size == expected["bytes"]
    assert verify_pack(installed / "pack.db", installed / "manifest.json")
    with open_db(installed / "pack.db") as conn:
        places = conn.execute("SELECT COUNT(*) FROM geo_places").fetchone()[0]
        aliases = conn.execute("SELECT COUNT(*) FROM geo_aliases").fetchone()[0]
        assert places == expected["place_count"]
        assert aliases == expected["alias_count"]
        row = conn.execute(
            "SELECT p.country_code FROM geo_aliases a JOIN geo_places p "
            "ON p.place_id=a.place_id WHERE a.search_key='tokyo' LIMIT 1").fetchone()
        assert row[0] == "JP"

    with pytest.raises(FileExistsError):
        activate_pack(directory, active_root)

    # A payload that does not hash to the manifest checksum is refused. The
    # placeholder stands in for the real database so the guard is exercised
    # without copying a gigabyte into the temporary directory.
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    (tampered / "pack.db").write_bytes(b"not the published database")
    shutil.copy2(directory / "manifest.json", tampered / "manifest.json")
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_pack(tampered / "pack.db", tampered / "manifest.json")
    with pytest.raises(ValueError, match="checksum mismatch"):
        activate_pack(tampered, tmp_path / "tampered-root")


def test_pack_registry_rejects_a_flipped_byte_in_a_real_pack(tmp_path):
    """One changed byte in a real pack is enough to fail the checksum."""
    expected = profile("COMPACT_GLOBAL")
    tampered = tmp_path / "tampered"
    tampered.mkdir()
    shutil.copy2(expected["path"], tampered / "pack.db")
    manifest = installed_manifest("COMPACT_GLOBAL")
    (tampered / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8")
    with open(tampered / "pack.db", "r+b") as handle:
        handle.seek(-1, os.SEEK_END)
        last = handle.read(1)
        handle.seek(-1, os.SEEK_END)
        handle.write(bytes([last[0] ^ 0xFF]))
    with pytest.raises(ValueError, match="checksum mismatch"):
        verify_pack(tampered / "pack.db", tampered / "manifest.json")
    with pytest.raises(ValueError, match="checksum mismatch"):
        activate_pack(tampered, tmp_path / "tampered-root")


def test_real_build_report_alias_language_counts_match_the_databases():
    """The published build report describes the databases that actually exist."""
    report_path = PACK_ROOT / LAYOUT["report"]
    if not report_path.is_file():
        pytest.skip("build_report.json not present")
    report = json.loads(report_path.read_text(encoding="utf-8"))
    for name, expected in EXPECTED.items():
        if not expected["path"].is_file():
            pytest.skip(f"real {name} pack not present")
        with open_db(expected["path"]) as conn:
            breakdown = dict(conn.execute(
                "SELECT language, COUNT(*) FROM geo_aliases GROUP BY language"))
        assert breakdown == report["profiles"][name]["alias_language_counts"]
