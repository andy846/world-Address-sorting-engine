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
if str(ROOT / "tools") not in sys.path:
    sys.path.insert(0, str(ROOT / "tools"))

from world_address_engine.data.pack_registry import install_pack, verify_pack, write_manifest
from build_reference_pack import manifest_from_report


def main():
    p = argparse.ArgumentParser(description="Install a GeoNames reference pack offline")
    p.add_argument("--database", type=Path)
    p.add_argument("--manifest", type=Path, help="Per-pack manifest JSON")
    p.add_argument("--build-report", type=Path,
                   help="build_report.json to derive the manifest from")
    p.add_argument("--profile", choices=["COMPACT_GLOBAL", "EXTENDED_GLOBAL"],
                   help="Profile to read from --build-report")
    p.add_argument("--active-root", type=Path)
    p.add_argument("--source-date", help="the pinned GeoNames snapshot date of the "
                                         "sources the pack was built from")
    p.add_argument("--pack-format-version", help="the key format generation of the "
                                                 "pack: k1 for the legacy "
                                                 "punctuation bearing packs, k2 for "
                                                 "the current one")
    p.add_argument("--refresh-manifest", type=Path,
                   help="rewrite the manifest of an installed pack directory from "
                        "the build report, after re-verifying its bytes")
    a = p.parse_args()
    if a.manifest:
        manifest = json.loads(a.manifest.read_text(encoding="utf-8"))
    elif a.build_report and a.profile:
        report = json.loads(a.build_report.read_text(encoding="utf-8"))
        manifest = manifest_from_report(report, a.profile,
                                        source_date=a.source_date,
                                        pack_format_version=a.pack_format_version)
    else:
        p.error("supply --manifest or both --build-report and --profile")
    if a.refresh_manifest:
        directory = a.refresh_manifest
        database = directory / "pack.db"
        if not database.is_file():
            raise SystemExit(f"no pack.db in {directory}")
        # The refreshed manifest has to describe the bytes that are there.
        verify_pack(database, directory / "manifest.json")
        if manifest.get("db_sha256") != json.loads(
                (directory / "manifest.json").read_text(encoding="utf-8"))["db_sha256"]:
            raise SystemExit(
                "the refreshed manifest does not describe the installed bytes")
        write_manifest(directory / "manifest.json", manifest)
        verify_pack(database, directory / "manifest.json")
        print(json.dumps({
            "refreshed_manifest": str(directory / "manifest.json"),
            "pack_id": manifest.get("pack_id"),
            "pack_version": manifest.get("pack_version"),
            "pack_format_version": manifest.get("pack_format_version"),
            "db_sha256": manifest.get("db_sha256"),
        }, ensure_ascii=False, indent=2))
        return
    if a.database is None:
        p.error("--database is required to install a pack")
    if a.active_root is None:
        p.error("--active-root is required to install a pack")
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
