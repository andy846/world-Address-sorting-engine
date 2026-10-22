"""Construct small, trilingual-focused GeoNames SQLite packs from LOCAL files.

No network accesses. GeoNames names do not independently verify postal codes.
City/administrative identifiers are preserved, while irrelevant feature types
and unsupported-language alternates are omitted from the search index.
"""

import os
import sqlite3
import tempfile
import unicodedata
import zipfile
from io import TextIOWrapper
from pathlib import Path

PROFILES = frozenset({"COMPACT_GLOBAL", "EXTENDED_GLOBAL"})
ALIAS_LANGS = frozenset({"en", "zh", "zh-CN", "zh-TW", "zh-Hans", "zh-Hant"})
BATCH_SIZE = 10000


def _is_latin_word(text: str) -> bool:
    return bool(text.strip()) and all(
        not char.isalpha() or unicodedata.name(char, "").startswith("LATIN ")
        for char in text
    )


def _search_key(text: str) -> str:
    return " ".join(text.strip().casefold().split())


def _insert_alias(conn: sqlite3.Connection, place_id: int, alias: str, language: str) -> None:
    alias = alias.strip()
    if not alias or len(alias) > 512:
        return
    conn.execute(
        """INSERT OR IGNORE INTO geo_aliases(place_id, alias, search_key, language)
            SELECT place_id, ?, ?, ? FROM geo_places WHERE place_id=?""",
        (alias, _search_key(alias), language, place_id),
    )


def _lines(path: Path):
    """Read .txt directly or stream the matching GeoNames .zip member."""
    if path.is_file():
        with path.open("r", encoding="utf-8", errors="strict") as f:
            for line in f:
                if line and not line.startswith("#"):
                    yield line.rstrip("\r\n").split("\t")
    else:
        archive = path.with_suffix(".zip")
        if not archive.is_file():
            raise FileNotFoundError(f"GeoNames source missing: {path} or {archive}")
        with zipfile.ZipFile(archive) as zf:
            if path.name not in zf.namelist():
                raise ValueError(f"GeoNames ZIP missing {path.name}: {archive}")
            with zf.open(path.name) as binary, TextIOWrapper(binary, encoding="utf-8") as stream:
                for line in stream:
                    if line and not line.startswith("#"):
                        yield line.rstrip("\r\n").split("\t")


def _compact_ids(path: Path) -> set[int]:
    if not path.is_file() and not path.with_suffix(".zip").is_file():
        raise FileNotFoundError(f"GeoNames cities1000 source missing: {path}")
    return {int(parts[0]) for parts in _lines(path) if len(parts) >= 9 and parts[0].isdigit()}


def build_geonames_pack(source_dir: Path, target_db: Path, profile: str) -> dict[str, int]:
    """Build GeoNames index from frozen, predownloaded allCountries and alternateNamesV2.

    In COMPACT_GLOBAL, include the cities1000 populated-place subset and every
    administrative hierarchy row from allCountries. EXTENDED_GLOBAL includes
    every populated-place and administrative row, excluding unrelated features.
    No broad street, building or other-language alias import is performed.
    """
    if profile not in PROFILES:
        raise ValueError("profile must be COMPACT_GLOBAL or EXTENDED_GLOBAL")
    source_dir, target_db = Path(source_dir), Path(target_db)
    main_file = source_dir / "allCountries.txt"
    alternate_file = source_dir / "alternateNamesV2.txt"
    if any(not p.is_file() and not p.with_suffix(".zip").is_file() for p in (main_file, alternate_file)):
        raise FileNotFoundError("GeoNames allCountries and alternateNamesV2 .zip/.txt sources required")
    compact = _compact_ids(source_dir / "cities1000.txt") if profile == "COMPACT_GLOBAL" else None
    target_db.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=".geonames-", suffix=".db", dir=target_db.parent)
    os.close(fd)
    temporary_db = Path(name)
    try:
        with sqlite3.connect(temporary_db) as conn:
            conn.execute("PRAGMA journal_mode=DELETE")
            conn.execute("""CREATE TABLE geo_places (
                place_id INTEGER PRIMARY KEY, name TEXT NOT NULL,
                country_code TEXT NOT NULL, admin1_code TEXT NOT NULL,
                admin2_code TEXT NOT NULL, feature_class TEXT NOT NULL,
                feature_code TEXT NOT NULL, population INTEGER NOT NULL
            )""")
            conn.execute("""CREATE TABLE geo_aliases (
                place_id INTEGER NOT NULL, alias TEXT NOT NULL,
                search_key TEXT NOT NULL, language TEXT NOT NULL,
                UNIQUE (place_id, search_key)
            )""")
            conn.execute("CREATE TABLE pack_metadata (profile TEXT NOT NULL)")
            conn.execute("INSERT INTO pack_metadata VALUES (?)", (profile,))
            batch = []
            for cols in _lines(main_file):
                if len(cols) < 15 or cols[6] not in ("A", "P"):
                    continue
                if not cols[0].isdigit() or not cols[8]:
                    continue
                if cols[6] == "P" and compact is not None and int(cols[0]) not in compact:
                    continue
                try:
                    population = int(cols[14] or "0")
                except ValueError:
                    population = 0
                batch.append((int(cols[0]), cols[1], cols[8], cols[10], cols[11], cols[6], cols[7], population))
                if len(batch) >= BATCH_SIZE:
                    conn.executemany("INSERT INTO geo_places VALUES (?,?,?,?,?,?,?,?)", batch)
                    batch.clear()
            if batch:
                conn.executemany("INSERT INTO geo_places VALUES (?,?,?,?,?,?,?,?)", batch)
            # Original GeoNames name is accepted if it is Latin-script; for
            # Chinese territories, native Han name is acceptable as Chinese.
            for place_id, name, country in conn.execute("SELECT place_id, name, country_code FROM geo_places"):
                if _is_latin_word(name):
                    _insert_alias(conn, place_id, name, "source-latin")
                elif country in ("CN", "HK", "MO", "TW"):
                    _insert_alias(conn, place_id, name, "source-zh")
            # Source ASCII transliterations survive even when native name is
            # Japanese, Korean, Cyrillic, etc. This is critical for English mail.
            for cols in _lines(main_file):
                if len(cols) >= 3 and cols[0].isdigit() and _is_latin_word(cols[2]):
                    _insert_alias(conn, int(cols[0]), cols[2], "ascii")
            for cols in _lines(alternate_file):
                if len(cols) >= 4 and cols[1].isdigit() and cols[2] in ALIAS_LANGS:
                    _insert_alias(conn, int(cols[1]), cols[3], cols[2])
            conn.execute("CREATE INDEX idx_geo_alias_key ON geo_aliases(search_key, place_id)")
            conn.execute("CREATE INDEX idx_geo_country_admin ON geo_places(country_code, admin1_code, admin2_code)")
            conn.commit()
            conn.execute("ANALYZE")
            conn.execute("VACUUM")
            if conn.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("GeoNames SQLite integrity_check failed")
            place_count = conn.execute("SELECT COUNT(*) FROM geo_places").fetchone()[0]
            alias_count = conn.execute("SELECT COUNT(*) FROM geo_aliases").fetchone()[0]
        os.replace(temporary_db, target_db)
        return {"place_count": place_count, "alias_count": alias_count, "sqlite_bytes": target_db.stat().st_size}
    finally:
        temporary_db.unlink(missing_ok=True)
