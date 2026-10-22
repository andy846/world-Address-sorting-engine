"""Build and measure full GeoNames SQLite packs from official local ZIPs.

python tools/download_geonames.py --source-dir data/geonames
python tools/build_reference_pack.py --source-dir data/geonames --output-dir builds --both --compress

Offline processing. Missing data causes FAIL, not a fabricated tiny DB.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sqlite3
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from world_address_engine.data.geonames_builder import (
    PACK_FORMAT_VERSION,
    build_geonames_pack,
    pack_manifest,
)
from world_address_engine.sqlite_util import open_db

SOURCE = "https://download.geonames.org/export/dump/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def manifest_from_report(report: dict, profile: str, *,
                          source_date: str | None = None,
                          pack_format_version: str | None = None) -> dict:
    """Derive the installable manifest from a build report.

    The report and the manifest are two views of one measurement. The
    installer derives its manifest from the report, so both have to be
    produced by the same code, otherwise a pack can be installed under a
    checksum that was never measured.

    The snapshot date and the key format generation are read **from the
    report**, never from the current source tree. A report that does not
    carry them is refused: guessing them would label a legacy database with
    the generation of today's builder, so two different databases would claim
    the same immutable version -- and the legacy one would then silently
    answer fewer queries than the reader expects, because its search keys
    still carry the punctuation of the source names.
    """
    if profile not in report.get("profiles", {}):
        raise KeyError(f"the report has no profile {profile}")
    resolved_date = source_date or report.get("source_date")
    if not resolved_date:
        raise KeyError(
            "the report carries no source_date; the snapshot date of the "
            "sources cannot be guessed. Pass --source-date explicitly.")
    resolved_format = pack_format_version or report.get("pack_format_version")
    if not resolved_format:
        raise KeyError(
            "the report carries no pack_format_version; the key format "
            "generation cannot be guessed, because a legacy database would "
            "then be published under today's generation. Pass "
            "--pack-format-version explicitly.")
    built = report["profiles"][profile]
    return pack_manifest(
        profile,
        {"place_count": built["place_count"],
         "alias_count": built["alias_count"],
         "sqlite_bytes": built["sqlite_bytes"],
         "alias_count_by_language": built["alias_language_counts"]},
        report["sources"],
        resolved_date,
        built["db_sha256"],
        pack_format_version=resolved_format,
        built_at=report.get("built_utc"),
        sqlite_version=report.get("sqlite_version"))


def build(source_dir: Path, output_dir: Path, profiles: list[str], compress: bool,
          source_date: str | None = None,
          pack_format_version: str = PACK_FORMAT_VERSION) -> dict:
    output_dir.mkdir(parents=True, exist_ok=True)
    sources = {}
    for name in ("allCountries", "alternateNamesV2", "cities1000"):
        match = next((x for suffix in (".zip", ".txt")
                      if (x := source_dir / (name + suffix)).exists()), None)
        if not match:
            if name == "cities1000" and "COMPACT_GLOBAL" not in profiles:
                continue
            raise FileNotFoundError("Missing official GeoNames source: " + name)
        sources[name] = {"filename": match.name, "bytes": match.stat().st_size,
                         "sha256": sha256(match), "url": SOURCE + match.name}
    source_date = source_date or _source_date(source_dir)
    report = {"source": "GeoNames", "license": "CC BY 4.0",
              "source_url": SOURCE, "built_utc": datetime.now(timezone.utc).isoformat(),
              "source_date": source_date, "pack_format_version": pack_format_version,
              "sqlite_version": sqlite3.sqlite_version,
              "sources": sources, "profiles": {}}
    for profile in profiles:
        filename = profile.lower() + ".sqlite"
        db = output_dir / filename
        if db.exists():
            raise FileExistsError(f"Already exists, build into fresh output folder: {db}")
        metrics = build_geonames_pack(source_dir, db, profile)
        actual = db.stat().st_size
        if metrics["sqlite_bytes"] != actual:
            raise ValueError("Measured SQLite byte size differs from builder")
        # The manifest needs the per language alias counts, the report needs
        # them under their own name. The counts are therefore taken out of
        # the metrics and handed to both explicitly.
        languages = dict(metrics.pop("alias_count_by_language", {}))
        with open_db(db) as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity verification failed")
        db_digest = sha256(db)
        detail = {"database": filename, **metrics,
                  "sqlite_mib": round(actual / 1048576, 3),
                  "db_sha256": db_digest, "alias_language_counts": languages}
        if compress:
            zipped = output_dir / (filename + ".zip")
            with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as zf:
                zf.write(db, arcname=filename)
            detail.update({"compressed_archive": zipped.name,
                           "compressed_bytes": zipped.stat().st_size,
                           "compressed_mib": round(zipped.stat().st_size / 1048576, 3)})
        report["profiles"][profile] = detail
        # The manifest is derived from the report, so the two can never
        # disagree about a checksum or a count.
        manifest = manifest_from_report(report, profile)
        (output_dir / (profile.lower() + ".manifest.json")).write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8")
    (output_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    return report


def _source_date(source_dir: Path) -> str:
    """Prefer the pinned retrieval date recorded when the sources were fetched."""
    manifest_path = Path(source_dir) / "source_manifest.json"
    if not manifest_path.is_file():
        raise ValueError("source_manifest.json required to pin the source date")
    date = json.loads(manifest_path.read_text(encoding="utf-8")).get("source_date")
    if not date:
        raise ValueError("source_manifest.json has no source_date; pass --source-date")
    return date


def sqlite_writer_version(database: Path) -> str:
    """The SQLite writer version that produced a database file.

    The writer version is stored in the file header, so the number is read
    from the bytes themselves rather than from the machine that happens to
    hold the file.
    """
    with Path(database).open("rb") as stream:
        header = stream.read(100)
    if len(header) < 100 or header[:16] != b"SQLite format 3\x00":
        raise ValueError(f"not a SQLite database: {database}")
    number = int.from_bytes(header[96:100], "big")
    return f"{number // 1000000}.{(number // 1000) % 1000}.{number % 1000}"


def stamp_report_provenance(report: dict, database: Path, *,
                            pack_format_version: str = PACK_FORMAT_VERSION) -> dict:
    """Complete the provenance of a report that was built before it carried it.

    A build report is the evidence a pack is installed from, so it has to
    state the snapshot date and the key format generation of the database it
    describes. A report written before those fields existed cannot be
    guessed at: a guess would publish a legacy database under the generation
    of today's builder. The generation is therefore supplied by the caller,
    and the SQLite writer version is read from the database header, so the
    completed report describes the bytes that are actually there.
    """
    stamped = dict(report)
    stamped.setdefault("pack_format_version", pack_format_version)
    stamped["sqlite_version"] = sqlite_writer_version(database)
    return stamped


def main():
    p = argparse.ArgumentParser(description="Build and MEASURE real GeoNames global SQLite files")
    p.add_argument("--source-dir", type=Path)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--output", type=Path, help="legacy single DB output path")
    p.add_argument("--profile", choices=["COMPACT_GLOBAL", "EXTENDED_GLOBAL"], default="COMPACT_GLOBAL")
    p.add_argument("--both", action="store_true")
    p.add_argument("--compress", action="store_true")
    p.add_argument("--source-date", help="Pinned GeoNames snapshot date (YYYY-MM-DD)")
    p.add_argument("--pack-format-version", default=PACK_FORMAT_VERSION,
                   help="key format generation of the pack (k1 for the legacy "
                        "punctuation bearing packs, k2 for the current one)")
    p.add_argument("--stamp-report", type=Path,
                   help="complete the provenance of an existing build_report.json")
    p.add_argument("--database", type=Path,
                   help="the database the stamped report describes")
    a = p.parse_args()
    if a.stamp_report:
        if a.database is None:
            p.error("--stamp-report needs --database")
        report = json.loads(a.stamp_report.read_text(encoding="utf-8"))
        stamped = stamp_report_provenance(
            report, a.database, pack_format_version=a.pack_format_version)
        a.stamp_report.write_text(json.dumps(stamped, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        written = []
        for profile in stamped.get("profiles", {}):
            manifest = manifest_from_report(stamped, profile)
            target = a.stamp_report.parent / (profile.lower() + ".manifest.json")
            target.write_text(json.dumps(manifest, ensure_ascii=False, indent=2,
                                         sort_keys=True) + "\n", encoding="utf-8")
            written.append(str(target))
        print(json.dumps({"stamped_report": str(a.stamp_report),
                          "manifests": written,
                          "pack_format_version": stamped["pack_format_version"],
                          "sqlite_version": stamped["sqlite_version"]},
                         ensure_ascii=False, indent=2))
        return
    if a.source_dir is None:
        p.error("specify --source-dir")
    if a.output:
        if a.both: p.error("--both incompatible with --output")
        answer = build_geonames_pack(a.source_dir, a.output, a.profile)
    else:
        if a.output_dir is None: p.error("specify --output-dir")
        profiles = ["COMPACT_GLOBAL", "EXTENDED_GLOBAL"] if a.both else [a.profile]
        answer = build(a.source_dir, a.output_dir, profiles, a.compress, a.source_date,
                       a.pack_format_version)
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
