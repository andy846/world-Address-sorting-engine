from pathlib import Path

from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.sqlite_util import open_db


def _row(place_id: int, name: str, ascii_name: str, cls: str, code: str, country: str, admin1: str = "") -> str:
    fields = [str(place_id), name, ascii_name, "", "0", "0", cls, code, country, "", admin1, "", "", "", "100", "", "", "Asia/Tokyo", "2025-01-01"]
    return "\t".join(fields)


def make_sources(root: Path):
    (root / "allCountries.txt").write_text("\n".join([
        _row(1, "Tokyo", "Tokyo", "P", "PPL", "JP", "40"),
        _row(2, "Shinjuku", "Shinjuku", "P", "PPL", "JP", "40"),
        _row(3, "Minor Hamlet", "Minor Hamlet", "P", "PPL", "GB", "01"),
        _row(4, "Moscow", "Moscow", "P", "PPL", "RU", "48"),
        _row(5, "Mount Fuji", "Mount Fuji", "T", "MT", "JP"),
        _row(6, "東京", "Dongjing", "P", "PPL", "JP", "40"),
    ]) + "\n", encoding="utf-8")
    (root / "cities1000.txt").write_text("\n".join([
        _row(1, "Tokyo", "Tokyo", "P", "PPL", "JP", "40"),
        _row(2, "Shinjuku", "Shinjuku", "P", "PPL", "JP", "40"),
    ]) + "\n", encoding="utf-8")
    (root / "alternateNamesV2.txt").write_text("\n".join([
        "10\t1\ten\tTokyo", "11\t1\tzh-TW\t東京", "12\t1\tzh-CN\t东京",
        "13\t1\tja\tとうきょう", "14\t4\tru\tМосква", "15\t4\ten\tMoscow",
        "16\t2\ten\tShinjuku", "17\t3\ten\tMinor Hamlet",
    ]) + "\n", encoding="utf-8")


def query(db: Path, sql: str):
    with open_db(db) as con:
        return con.execute(sql).fetchall()


def test_only_en_zh_and_latin_aliases_indexed(tmp_path):
    make_sources(tmp_path)
    db = tmp_path / "geo.db"
    stats = build_geonames_pack(tmp_path, db, "EXTENDED_GLOBAL")
    aliases = query(db, "SELECT alias FROM geo_aliases")
    names = {a[0] for a in aliases}
    assert {"Tokyo", "東京", "东京", "Moscow"} <= names
    assert "とうきょう" not in names
    assert "Москва" not in names
    assert stats["place_count"] == 5  # topographic feature discarded


def test_romanized_japanese_city_remains_searchable(tmp_path):
    make_sources(tmp_path)
    db = tmp_path / "geo.db"
    build_geonames_pack(tmp_path, db, "COMPACT_GLOBAL")
    assert query(db, "SELECT place_id FROM geo_aliases WHERE search_key='shinjuku'") == [(2,)]


def test_extended_retains_small_town_missing_from_compact(tmp_path):
    make_sources(tmp_path)
    small, extended = tmp_path / "small.db", tmp_path / "extended.db"
    build_geonames_pack(tmp_path, small, "COMPACT_GLOBAL")
    build_geonames_pack(tmp_path, extended, "EXTENDED_GLOBAL")
    assert query(small, "SELECT place_id FROM geo_places WHERE place_id=3") == []
    assert query(extended, "SELECT place_id FROM geo_places WHERE place_id=3") == [(3,)]


def test_packs_keep_same_destination_ids(tmp_path):
    make_sources(tmp_path)
    small, extended = tmp_path / "small.db", tmp_path / "extended.db"
    build_geonames_pack(tmp_path, small, "COMPACT_GLOBAL")
    build_geonames_pack(tmp_path, extended, "EXTENDED_GLOBAL")
    assert query(small, "SELECT country_code FROM geo_places WHERE place_id=1") == [("JP",)]
    assert query(extended, "SELECT country_code FROM geo_places WHERE place_id=1") == [("JP",)]


def test_explicit_language_tag_wins_over_the_derived_label(tmp_path):
    """An explicit 'en' alternate name must not be labelled 'source-latin'."""
    make_sources(tmp_path)
    db = tmp_path / "geo.db"
    build_geonames_pack(tmp_path, db, "EXTENDED_GLOBAL")
    assert query(db, "SELECT language FROM geo_aliases "
                     "WHERE place_id=1 AND search_key='tokyo'") == [("en",)]
    assert query(db, "SELECT language FROM geo_aliases "
                     "WHERE place_id=2 AND search_key='shinjuku'") == [("en",)]


def test_source_name_is_labelled_when_no_explicit_tag_exists(tmp_path):
    (tmp_path / "allCountries.txt").write_text(
        _row(1, "Springfield", "Springfield", "P", "PPL", "US", "IL") + "\n", encoding="utf-8")
    (tmp_path / "alternateNamesV2.txt").write_text("", encoding="utf-8")
    db = tmp_path / "geo.db"
    build_geonames_pack(tmp_path, db, "EXTENDED_GLOBAL")
    # No explicit tag exists, so the derived label must still describe the row.
    assert query(db, "SELECT language FROM geo_aliases "
                     "WHERE place_id=1 AND search_key='springfield'") == [("source-latin",)]
