"""GUI-only installed-pack discovery and fresh batch directories."""
from datetime import datetime
from pathlib import Path
import sys

from world_address_engine.jobs.country_analysis import _pack_metadata


def discovery_roots():
    return tuple(dict.fromkeys((Path(sys.executable).resolve().parent,
                               Path(__file__).resolve().parents[3], Path.cwd())))


def discover_pack(kind, *, roots=None):
    roots = discovery_roots() if roots is None else roots
    profiles = ('geonames-extended-global-*-k2', 'geonames-compact-global-*-k2') if kind == 'geo' else ('hk-bilingual-als-*',)
    for pattern in profiles:
        for root in roots:
            for folder in sorted((Path(root) / 'packs').glob(pattern), reverse=True):
                db = folder / 'pack.db'
                if db.is_file():
                    return str(db.resolve())
    return ''


def allocate_run_directory(source, parent=None, *, now=None):
    source = Path(source)
    parent = Path(parent) if parent else source.parent
    parent.mkdir(parents=True, exist_ok=True)
    name = f'{source.stem}_output_{(now or datetime.now()):%Y%m%d_%H%M%S}'
    index = 0
    while True:
        folder = parent / (name if index == 0 else f'{name}_{index:02d}')
        try:
            folder.mkdir(mode=0o700)
            return folder.resolve()
        except FileExistsError:
            index += 1


def preflight_references(geo, hk=None):
    """Validate and pin consumed reference bytes before reserving output."""
    from world_address_engine.data.pack_registry import verify_pack
    from world_address_engine.data.hk_regional import hk_pack_metadata
    from world_address_engine.jobs.checkpoint import file_sha256
    geo = Path(geo)
    manifest = geo.with_name('manifest.json')
    geo_digest = file_sha256(geo)
    manifest_digest = file_sha256(manifest) if manifest.is_file() else None
    if manifest_digest is not None:
        verify_pack(geo, manifest)
    metadata = _pack_metadata(geo, geo_digest)
    if metadata['profile'] not in ('COMPACT_GLOBAL', 'EXTENDED_GLOBAL'):
        raise ValueError('Choose a readable global GeoNames pack with a valid global profile.')
    regional = hk_pack_metadata(Path(hk)) if hk else None
    # Validators may read several files; pin the bytes they consumed, then
    # recheck them together before handing the identity to the job runner.
    if (file_sha256(geo) != geo_digest or
            (file_sha256(manifest) if manifest.is_file() else None) != manifest_digest or
            metadata['geo_manifest_sha256'] != manifest_digest):
        raise ValueError('Global reference pack changed during verification')
    if regional is not None:
        path = Path(regional['path'])
        coverage = regional.get('source_validation', {})
        if (file_sha256(path) != regional['db_sha256'] or
                file_sha256(path.with_name('manifest.json')) != regional['manifest_sha256'] or
                (coverage.get('quarantine_file') and
                 file_sha256(path.with_name(coverage['quarantine_file'])) != coverage['quarantine_sha256'])):
            raise ValueError('Hong Kong reference pack changed during verification')
    return {'geo_sha256': geo_digest, 'geo_manifest_sha256': manifest_digest,
            'hk_regional': regional}
