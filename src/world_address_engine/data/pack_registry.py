"""Integrity checking and atomic local installation for offline reference packs."""

import hashlib
import json
import os
import re
import shutil
import tempfile
from pathlib import Path

from world_address_engine.data.geonames_builder import (
    LEGACY_PACK_FORMAT_VERSION,
    PACK_FORMAT_VERSION,
)
from world_address_engine.sqlite_util import open_db

REQUIRED = {
    "pack_id", "profile", "pack_version", "schema_version", "created_at",
    "source_date", "source_sha256", "db_sha256", "record_count",
    "alias_count_by_language", "attribution", "license",
}

PACK_DB_NAME = "pack.db"
PACK_MANIFEST_NAME = "manifest.json"

# The reader folds the punctuation of a name away, so it looks up
# "st john s". A pack built by the legacy builder stores "st. john s", and
# every lookup of a punctuated name would silently find nothing. The two
# generations are told apart by the manifest when it declares one, and by
# the keys themselves otherwise: a key that is plain printable ASCII but
# carries something other than a lowercase letter, a digit or a space is a
# punctuation bearing key of the legacy generation.
LEGACY_KEY_PROBE = (
    "SELECT 1 FROM geo_aliases WHERE search_key NOT GLOB '*[^ -~]*' "
    "AND search_key GLOB '*[^a-z0-9 ]*' LIMIT 1")


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


def canonical_manifest(manifest: dict) -> str:
    """Deterministic manifest text so the same inputs always produce the same bytes."""
    return json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def manifest_format_version(manifest: dict) -> str:
    """The key format generation a manifest declares, if it declares one."""
    return str(manifest.get("pack_format_version") or "")


def require_readable_pack(pack_db: Path) -> str:
    """Refuse a pack whose search keys this reader cannot reach.

    The reader folds the punctuation of a name away, so it looks up
    "st john s". A pack of the legacy generation stores "st. john s", and
    every lookup of a punctuated name would silently find nothing -- the run
    would answer fewer questions than the caller asked, without ever saying
    so. Such a pack is refused here instead.

    The generation is read from the manifest when it declares one, and from
    the keys themselves otherwise, so a pack without a manifest is checked
    just as strictly as one with it.
    """
    pack_db = Path(pack_db)
    manifest_path = pack_db.with_name(PACK_MANIFEST_NAME)
    if manifest_path.is_file():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        declared = manifest_format_version(manifest)
        if declared:
            if declared != PACK_FORMAT_VERSION:
                raise ValueError(
                    f"the reference pack {pack_db} declares the search key "
                    f"format {declared!r}, but this reader speaks "
                    f"{PACK_FORMAT_VERSION!r}. The two cannot be mixed: a "
                    f"lookup would silently find nothing.")
            return declared
    with open_db(pack_db) as conn:
        legacy = conn.execute(LEGACY_KEY_PROBE).fetchone() is not None
    if legacy:
        raise ValueError(
            f"the reference pack {pack_db} stores the legacy, punctuation "
            f"bearing search keys (generation {LEGACY_PACK_FORMAT_VERSION!r}). "
            f"This reader folds the punctuation away and would silently find "
            f"nothing for every punctuated name. Install a pack of generation "
            f"{PACK_FORMAT_VERSION!r}.")
    return PACK_FORMAT_VERSION


def write_manifest(manifest_path: Path, manifest: dict) -> Path:
    """Write a manifest atomically so a reader never sees a partial file."""
    manifest_path = Path(manifest_path)
    manifest_path.parent.mkdir(parents=True, exist_ok=True)
    pending = manifest_path.with_name(manifest_path.name + ".pending")
    pending.write_text(canonical_manifest(manifest), encoding="utf-8")
    os.replace(pending, manifest_path)
    return manifest_path


def stage_pack(db_path: Path, manifest: dict, staging_dir: Path) -> Path:
    """Lay a built database out as an installable pack directory.

    The GeoNames builder publishes `<profile>.sqlite`, while the installer
    expects `pack.db` next to `manifest.json`. Staging reconciles the two and
    refuses a payload whose bytes do not match the manifest checksum.
    """
    db_path, staging_dir = Path(db_path), Path(staging_dir)
    if not db_path.is_file():
        raise FileNotFoundError(db_path)
    staging_dir.mkdir(parents=True, exist_ok=True)
    target = staging_dir / PACK_DB_NAME
    if target.exists():
        target.unlink()
    try:
        os.link(db_path, target)
    except OSError:
        shutil.copy2(db_path, target)
    write_manifest(staging_dir / PACK_MANIFEST_NAME, manifest)
    verify_pack(target, staging_dir / PACK_MANIFEST_NAME)
    return staging_dir


def install_pack(db_path: Path, manifest: dict, active_root: Path) -> Path:
    """Stage a built database, then publish it as an immutable versioned pack."""
    db_path, active_root = Path(db_path), Path(active_root)
    active_root.mkdir(parents=True, exist_ok=True)
    staging_dir = Path(tempfile.mkdtemp(prefix=".staging-", dir=active_root))
    try:
        stage_pack(db_path, manifest, staging_dir)
        return activate_pack(staging_dir, active_root)
    finally:
        shutil.rmtree(staging_dir, ignore_errors=True)


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
