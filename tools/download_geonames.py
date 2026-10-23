"""Download official GeoNames archives for an offline SQLite build.

Source: https://download.geonames.org/export/dump/ — CC BY 4.0.
This command connects to the internet only during data preparation; the
address classifier itself never requires online access.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path
import tempfile
from urllib.request import urlopen
import zipfile

SOURCE = "https://download.geonames.org/export/dump/"
FILES = ("allCountries.zip", "alternateNamesV2.zip", "cities1000.zip")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def download_sources(source_dir: Path) -> dict:
    source_dir = Path(source_dir)
    source_dir.mkdir(parents=True, exist_ok=True)
    retrieved = datetime.now(timezone.utc)
    manifest = {"source": "GeoNames", "license": "CC BY 4.0",
                "retrieved_utc": retrieved.isoformat(),
                "source_date": retrieved.date().isoformat(),
                "files": {}}
    for filename in FILES:
        dest = source_dir / filename
        if not dest.exists():
            fd, name = tempfile.mkstemp(dir=source_dir, prefix=".download-", suffix=".zip")
            os.close(fd)
            tmp = Path(name)
            try:
                with urlopen(SOURCE + filename, timeout=120) as download, tmp.open("wb") as out:
                    while block := download.read(1024 * 1024):
                        out.write(block)
                    out.flush()
                    os.fsync(out.fileno())
                with zipfile.ZipFile(tmp) as archive:
                    if filename.removesuffix(".zip") + ".txt" not in archive.namelist():
                        raise ValueError("unexpected GeoNames ZIP content: " + filename)
                    if bad := archive.testzip():
                        raise ValueError("corrupted GeoNames member: " + bad)
                os.replace(tmp, dest)
            finally:
                tmp.unlink(missing_ok=True)
        with zipfile.ZipFile(dest) as archive:
            if filename.removesuffix(".zip") + ".txt" not in archive.namelist():
                raise ValueError("missing expected GeoNames file: " + filename)
            if bad := archive.testzip():
                raise ValueError("corrupt member: " + bad)
        manifest["files"][filename] = {"url": SOURCE + filename, "bytes": dest.stat().st_size,
                                        "sha256": sha256(dest)}
    tmp_manifest = source_dir / ".source-manifest.pending"
    tmp_manifest.write_text(json.dumps(manifest, indent=2), encoding="utf8")
    os.replace(tmp_manifest, source_dir / "source_manifest.json")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Download official GeoNames source ZIPs")
    parser.add_argument("--source-dir", type=Path, required=True)
    args = parser.parse_args()
    print(json.dumps(download_sources(args.source_dir), indent=2))
