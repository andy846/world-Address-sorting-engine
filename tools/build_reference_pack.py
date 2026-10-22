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
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))
from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.sqlite_util import open_db

SOURCE = "https://download.geonames.org/export/dump/"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def build(source_dir: Path, output_dir: Path, profiles: list[str], compress: bool) -> dict:
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
    report = {"source": "GeoNames", "license": "CC BY 4.0",
              "source_url": SOURCE, "built_utc": datetime.now(timezone.utc).isoformat(),
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
        with open_db(db) as con:
            if con.execute("PRAGMA integrity_check").fetchone()[0] != "ok":
                raise ValueError("SQLite integrity verification failed")
            languages = dict(con.execute("SELECT language,COUNT(*) FROM geo_aliases GROUP BY language"))
        detail = {"database": filename, **metrics,
                  "sqlite_mib": round(actual / 1048576, 3),
                  "db_sha256": sha256(db), "alias_language_counts": languages}
        if compress:
            zipped = output_dir / (filename + ".zip")
            with zipfile.ZipFile(zipped, "w", compression=zipfile.ZIP_DEFLATED,
                                 compresslevel=6, allowZip64=True) as zf:
                zf.write(db, arcname=filename)
            detail.update({"compressed_archive": zipped.name,
                           "compressed_bytes": zipped.stat().st_size,
                           "compressed_mib": round(zipped.stat().st_size / 1048576, 3)})
        report["profiles"][profile] = detail
    (output_dir / "build_report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf8")
    return report


def main():
    p = argparse.ArgumentParser(description="Build and MEASURE real GeoNames global SQLite files")
    p.add_argument("--source-dir", type=Path, required=True)
    p.add_argument("--output-dir", type=Path)
    p.add_argument("--output", type=Path, help="legacy single DB output path")
    p.add_argument("--profile", choices=["COMPACT_GLOBAL", "EXTENDED_GLOBAL"], default="COMPACT_GLOBAL")
    p.add_argument("--both", action="store_true")
    p.add_argument("--compress", action="store_true")
    a = p.parse_args()
    if a.output:
        if a.both: p.error("--both incompatible with --output")
        answer = build_geonames_pack(a.source_dir, a.output, a.profile)
    else:
        if a.output_dir is None: p.error("specify --output-dir")
        profiles = ["COMPACT_GLOBAL", "EXTENDED_GLOBAL"] if a.both else [a.profile]
        answer = build(a.source_dir, a.output_dir, profiles, a.compress)
    print(json.dumps(answer, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
