"""Integrity checking and atomic local installation for offline reference packs."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

REQUIRED = {
    "pack_id", "profile", "pack_version", "schema_version", "created_at",
    "source_date", "source_sha256", "db_sha256", "record_count",
    "alias_count_by_language", "attribution", "license",
}


def _sha256(path: Path) -> str:
    sha = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()


def verify_pack(db_path: Path, manifest_path: Path) -> bool:
    """Require valid source metadata and a matching hash before activation."""
    db_path, manifest_path = Path(db_path), Path(manifest_path)
    if not db_path.is_file() or not manifest_path.is_file():
        raise FileNotFoundError("pack.db and manifest.json both required")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not REQUIRED <= manifest.keys():
        raise ValueError("incomplete data pack manifest")
    for key in ("pack_id", "pack_version"):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,79}", str(manifest[key])):
            raise ValueError(f"unsafe {key}")
    for key in ("db_sha256", "source_sha256"):
        if not re.fullmatch(r"[a-f0-9]{64}", str(manifest[key])):
            raise ValueError(f"invalid {key} checksum")
    if manifest["schema_version"] != 1 or manifest["record_count"] < 0:
        raise ValueError("unsupported schema or invalid record_count")
    if _sha256(db_path) != manifest["db_sha256"]:
        raise ValueError("data pack checksum mismatch")
    return True


def activate_pack(staging_dir: Path, active_root: Path) -> Path:
    """Copy into root's temporary directory, verify, then atomically publish."""
    staging_dir, active_root = Path(staging_dir), Path(active_root)
    verify_pack(staging_dir / "pack.db", staging_dir / "manifest.json")
    meta = json.loads((staging_dir / "manifest.json").read_text(encoding="utf-8"))
    active_root.mkdir(parents=True, exist_ok=True)
    installed = active_root / f"{meta['pack_id']}-{meta['pack_version']}"
    if installed.exists():
        raise FileExistsError("pack version already installed; do not overwrite immutable pack")
    temporary = Path(tempfile.mkdtemp(prefix=".new-pack-", dir=active_root))
    try:
        shutil.copy2(staging_dir / "pack.db", temporary / "pack.db")
        shutil.copy2(staging_dir / "manifest.json", temporary / "manifest.json")
        verify_pack(temporary / "pack.db", temporary / "manifest.json")
        if installed.exists():
            raise FileExistsError("race: pack version already installed")
        os.rename(temporary, installed)
        return installed
    finally:
        if temporary.exists():
            shutil.rmtree(temporary)
