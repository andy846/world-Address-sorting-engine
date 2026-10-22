"""Install a built GeoNames reference pack offline, from local files only.

    python tools/install_reference_pack.py \
        --database builds/global-2026-10-22/compact_global.sqlite \
        --manifest builds/global-2026-10-22/compact_global.manifest.json \
        --active-root packs/

The database checksum recorded in the manifest is verified before publication,
and the pack is published atomically as an immutable versioned directory.
No network access is performed.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "src") not in sys.path:
    sys.path.insert(0, str(ROOT / "src"))

from world_address_engine.data.geonames_builder import pack_manifest
from world_address_engine.data.pack_registry import install_pack


def main():
    p = argparse.ArgumentParser(description="Install a GeoNames reference pack offline")
    p.add_argument("--database", type=Path, required=True)
    p.add_argument("--manifest", type=Path, help="Per-pack manifest JSON")
    p.add_argument("--build-report", type=Path,
                   help="build_report.json to derive the manifest from")
    p.add_argument("--profile", choices=["COMPACT_GLOBAL", "EXTENDED_GLOBAL"],
                   help="Profile to read from --build-report")
    p.add_argument("--active-root", type=Path, required=True)
    a = p.parse_args()
    if a.manifest:
        manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    elif a.build_report and a.profile:
        report = json.loads(a.build_report.read_text(encoding="utf-8"))
        built = report["profiles"][a.profile]
        manifest = pack_manifest(
            a.profile,
            {"place_count": built["place_count"],
             "alias_count": built["alias_count"],
             "sqlite_bytes": built["sqlite_bytes"],
             "alias_count_by_language": built["alias_language_counts"]},
            report["sources"],
            report.get("source_date") or "2026-10-22",
            built["db_sha256"],
        )
    else:
        p.error("supply --manifest or both --build-report and --profile")
    installed = install_pack(a.database, manifest, a.active_root)
    print(json.dumps({
        "installed_pack": str(installed),
        "pack_id": manifest.get("pack_id"),
        "pack_version": manifest.get("pack_version"),
        "profile": manifest.get("profile"),
        "db_sha256": manifest.get("db_sha256"),
        "record_count": manifest.get("record_count"),
    }, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
