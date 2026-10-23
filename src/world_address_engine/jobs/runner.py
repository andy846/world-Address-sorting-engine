"""Offline streaming classifier with version-pinned, resumable output shards.

Production runs require a separately signed HKP approval manifest whose key
is held outside the repository. Without one the run is refused; the
catalogue database can never approve itself.
"""
from pathlib import Path
import json
import shutil

from world_address_engine.io.delimited import iter_csv_records, iter_txt_records
from world_address_engine.io.reports import write_reports
from world_address_engine.io.xlsx import iter_xlsx_records
from world_address_engine.data.pack_registry import require_readable_pack
from world_address_engine.hkp.approval import CatalogueApproval, load_approval
from world_address_engine.hkp.catalogue import approved_codes
from world_address_engine.matching.classify import classify_record
from world_address_engine.jobs.checkpoint import (
    atomic_json, commit_batch, committed_shards, file_sha256, iter_saved_pairs,
)


def _load_approval(manifest_path: Path | None, key_path: Path | None,
                   hkp_db: Path) -> CatalogueApproval | None:
    """Load the signed approval, or fail closed when it is absent."""
    if manifest_path is None and key_path is None:
        return None
    if manifest_path is None or key_path is None:
        raise ValueError('an approval manifest and its key must be supplied together')
    return load_approval(manifest_path, key_path, hkp_db)


# Bumped whenever the classification or reporting rules change. It is
# recorded in every export so a result can be traced to the rules that
# produced it.
RULES_VERSION = '2026-10-23.4'

# How often the cancel flag is read while a batch is still filling. A cancel
# must never be ignored because the job is smaller than one batch.
CANCEL_CHECK_INTERVAL = 500


def _code_validator(hkp_db: Path, approval: CatalogueApproval | None):
    """Bind every exported code to the approved catalogue.

    A checkpoint shard is local, writable data: its own digest lives in its
    filename, so a tampered shard can be renamed with a matching digest. The
    only trustworthy anchor is the approved catalogue, so every MATCHED row
    is re-checked against it before anything is published.
    """
    codes = approved_codes(hkp_db, approval)

    def validate(destination_id: str | None, code: str | None) -> bool:
        return bool(destination_id) and codes.get(destination_id) == code

    return validate


def _catalogue_version(hkp_db: Path) -> str:
    from world_address_engine.sqlite_util import open_db
    try:
        with open_db(hkp_db) as conn:
            row = conn.execute('SELECT catalogue_version FROM metadata').fetchone()
        return str(row[0]) if row else ''
    except Exception:
        return ''


def _geo_pack_versions(geo_db: Path) -> str:
    """The installed pack version, when the pack ships a manifest."""
    manifest = Path(geo_db).with_name('manifest.json')
    if manifest.is_file():
        try:
            data = json.loads(manifest.read_text(encoding='utf-8'))
        except (OSError, ValueError):
            data = {}
        version = data.get('pack_version')
        if version:
            return str(version)
    return 'sha256:' + file_sha256(Path(geo_db))[:16]


def _verify_shards(paths, cfg: dict, approval) -> None:
    """Re-derive every committed result and compare it with the shard.

    A shard is local, writable data. Its digest lives in its own filename,
    so a tamperer can rename a rewritten shard with a matching digest. The
    classification is deterministic, so re-running it over the committed
    records is the only complete local defence against a forged result.
    """
    geo = Path(cfg['geo_db'])
    hkp = Path(cfg['hkp_db'])
    for record, result in iter_saved_pairs(paths):
        again = classify_record(record, geo, hkp, approval)
        if (again.status, again.hkp_code, again.destination_id) != (
                result.status, result.hkp_code, result.destination_id):
            raise ValueError(
                f'checkpoint verification failed at record {record.record_no}: '
                'the committed result does not match a fresh classification')


def _remove_checkpoint(state: Path) -> None:
    """Remove plaintext checkpoints or fail without publishing COMPLETE."""
    if state.exists():
        shutil.rmtree(state)
    if state.exists():
        raise OSError(f'checkpoint cleanup failed; plaintext state remains at {state}')


def _records(input_path: Path, options: dict):
    kind = input_path.suffix.lower()
    encoding = options.get('encoding', 'utf-8-sig')
    columns = tuple(options.get('address_columns', ()))
    record_id_column = options.get('record_id_column')
    if kind == '.csv':
        return iter_csv_records(input_path, encoding, columns, record_id_column)
    if kind == '.txt':
        return iter_txt_records(input_path, encoding,
                                options.get('txt_mode', 'line'), options.get('delimiter'))
    if kind == '.xlsx':
        if not options.get('sheet_name'):
            raise ValueError('Excel input requires sheet_name')
        return iter_xlsx_records(input_path, options['sheet_name'], columns, record_id_column)
    raise ValueError('expected CSV, XLSX, or TXT input')


def _snapshot(input_path: Path, geo_db: Path, hkp_db: Path, options: dict, batch_size: int,
              testing: bool, approval: CatalogueApproval | None,
              approval_manifest: Path | None, approval_key: Path | None,
              keep_checkpoint: bool = False) -> dict:
    for p in (input_path, geo_db, hkp_db):
        if not p.is_file():
            raise FileNotFoundError(p)
    if batch_size < 1 or batch_size > 100_000:
        raise ValueError('batch_size must be 1 to 100000')
    if not testing:
        if approval is None:
            raise ValueError(
                'a signed HKP approval manifest and key are required for a production run')
        if not approval.is_production:
            raise ValueError(
                'the supplied HKP approval is a test fixture and cannot authorise production')
    return {
        'input_path': str(input_path.resolve()),
        'geo_db': str(geo_db.resolve()),
        'hkp_db': str(hkp_db.resolve()),
        'input_sha256': file_sha256(input_path),
        'geo_sha256': file_sha256(geo_db),
        'hkp_sha256': file_sha256(hkp_db),
        'input_options': options,
        'batch_size': batch_size,
        'allow_unverified_reference_data': testing,
        'approval_id': approval.approval_id if approval else None,
        'approval_scope': approval.scope if approval else None,
        'approval_manifest_sha256': approval.manifest_sha256 if approval else None,
        'approval_manifest_path': str(Path(approval_manifest).resolve()) if approval_manifest else None,
        'approval_key_path': str(Path(approval_key).resolve()) if approval_key else None,
        'keep_checkpoint': bool(keep_checkpoint),
        'rules_version': RULES_VERSION,
        'schema_version': 2,
    }


def _process(output_dir: Path, cfg: dict, *, max_batches: int | None = None,
             approval: CatalogueApproval | None = None,
             cancel=None, progress=None) -> dict:
    state = output_dir / '.job-state'
    paths, last_committed = committed_shards(
        state, expected_rules_version=RULES_VERSION)
    source = Path(cfg['input_path'])
    geo = Path(cfg['geo_db'])
    hkp = Path(cfg['hkp_db'])
    iterator = _records(source, cfg['input_options'])
    batch = []
    committed_new = 0
    since_check = 0

    def cancelled() -> bool:
        """Read the cancel flag once and reset the periodic counter."""
        nonlocal since_check
        since_check = 0
        return bool(cancel is not None and cancel())

    for record in iterator:
        if record.record_no <= last_committed:
            continue
        if record.record_no != last_committed + len(batch) + 1:
            raise ValueError('nonsequential source record')
        result = classify_record(record, geo, hkp, approval)
        batch.append((record, result))
        since_check += 1
        # A cancel must be honoured even when the job never fills a batch,
        # so the flag is polled on a record interval as well as at every
        # committed batch boundary.
        if since_check >= CANCEL_CHECK_INTERVAL and cancelled():
            return {'run_status': 'CANCELLED', 'committed_records': last_committed}
        if len(batch) >= cfg['batch_size']:
            commit_batch(state, batch, RULES_VERSION)
            last_committed = batch[-1][0].record_no
            batch.clear()
            committed_new += 1
            if progress is not None:
                progress(last_committed)
            if cancelled():
                return {'run_status': 'CANCELLED', 'committed_records': last_committed}
            if max_batches is not None and committed_new >= max_batches:
                return {'run_status':'PAUSED', 'committed_records': last_committed}
    # The trailing partial batch is never published after a cancel: the
    # uncommitted records are simply left for the next resume.
    if cancelled():
        return {'run_status': 'CANCELLED', 'committed_records': last_committed}
    if batch:
        commit_batch(state, batch, RULES_VERSION)
    paths, last_committed = committed_shards(
        state, expected_rules_version=RULES_VERSION)
    # Ensure the source files have not been edited DURING this run. The
    # startup snapshot alone cannot protect against mid-job changes.
    for label, key_path, key_hash in (
        ('input', 'input_path', 'input_sha256'),
        ('geo reference pack', 'geo_db', 'geo_sha256'),
        ('HKP reference catalogue', 'hkp_db', 'hkp_sha256'),
    ):
        if file_sha256(Path(cfg[key_path])) != cfg[key_hash]:
            raise ValueError(f'{label} changed during classification; job incomplete')
    if output_dir.joinpath('Run_Manifest.json').exists():
        raise FileExistsError('completed job already exists')
    # A checkpoint is local writable data. Re-derive every committed result
    # before publication; there is no safe option to skip this final check.
    _verify_shards(paths, cfg, approval)
    manifest_meta = {
        'production_approved': bool(
            not cfg['allow_unverified_reference_data']
            and cfg.get('approval_scope') == 'PRODUCTION'),
        'data_approval': ('TEST_ONLY_UNVERIFIED'
                          if cfg['allow_unverified_reference_data']
                          or cfg.get('approval_scope') != 'PRODUCTION'
                          else 'INDEPENDENTLY_AUDITED'),
        'approval_id': cfg.get('approval_id'),
        'approval_scope': cfg.get('approval_scope'),
        # The review panel is bound to the approval that authorised *this*
        # run, so the manifest must name it and pin its digest. The signing
        # key itself is never written to a published artefact.
        'approval_manifest_path': cfg.get('approval_manifest_path'),
        'approval_manifest_sha256': cfg.get('approval_manifest_sha256'),
        'input_sha256': cfg['input_sha256'],
        'geo_sha256': cfg['geo_sha256'],
        'hkp_sha256': cfg['hkp_sha256'],
        'batch_size': cfg['batch_size'],
        'catalogue_version': _catalogue_version(Path(cfg['hkp_db'])),
        'geo_pack_versions': _geo_pack_versions(Path(cfg['geo_db'])),
        'rules_version': RULES_VERSION,
    }
    before_manifest = None
    if not cfg.get('keep_checkpoint'):
        # Delete plaintext shards after report files are staged but before
        # publishing COMPLETE. A cleanup failure therefore leaves an
        # incomplete run, never a completed run with retained plaintext.
        before_manifest = lambda: _remove_checkpoint(state)
    counts = write_reports(
        iter_saved_pairs(paths), output_dir, manifest_meta,
        code_validator=_code_validator(Path(cfg['hkp_db']), approval),
        require_validated_codes=True, before_manifest=before_manifest)
    return counts


def run_job(input_path: Path, output_dir: Path, geo_db: Path, hkp_db: Path,
            input_options: dict, batch_size: int = 10_000, *,
            max_batches: int | None = None,
            allow_unverified_reference_data: bool = False,
            approval_manifest: Path | None = None,
            approval_key: Path | None = None,
            verify_shards: bool = True,
            keep_checkpoint: bool = False,
            cancel=None, progress=None) -> dict:
    """Start a new offline job. Explicit testing bypass leaves TEST_ONLY manifest."""
    if verify_shards is not True:
        raise ValueError('checkpoint shard verification is mandatory')
    input_path, output_dir, geo_db, hkp_db = map(Path, (input_path, output_dir, geo_db, hkp_db))
    if max_batches is not None and max_batches < 1:
        raise ValueError('max_batches must be positive')
    options = dict(input_options)
    approval = _load_approval(approval_manifest, approval_key, hkp_db)
    # A pack whose search keys this reader cannot reach would answer fewer
    # questions than the caller asked, without ever saying so.
    require_readable_pack(geo_db)
    # Validate before creating state; never issue an approved mailing export
    # against merely syntactically validated, unofficial fixture code tables.
    cfg = _snapshot(input_path, geo_db, hkp_db, options, batch_size,
                    allow_unverified_reference_data, approval,
                    approval_manifest, approval_key, keep_checkpoint)
    cfg['verify_shards'] = True
    state = output_dir / '.job-state'
    if state.exists() or output_dir.joinpath('Run_Manifest.json').exists():
        raise FileExistsError('existing job; use resume_job or a new output directory')
    output_dir.mkdir(parents=True, exist_ok=True)
    state.mkdir()
    atomic_json(state / 'config.json', cfg)
    return _process(output_dir, cfg, max_batches=max_batches, approval=approval,
                    cancel=cancel, progress=progress)


def resume_job(run_dir: Path, *, max_batches: int | None = None,
               verify_shards: bool | None = None,
               keep_checkpoint: bool | None = None,
               cancel=None, progress=None) -> dict:
    """Resume a paused/failed job ONLY if all source versions still match."""
    if verify_shards is False:
        raise ValueError('checkpoint shard verification is mandatory')
    if max_batches is not None and max_batches < 1:
        raise ValueError('max_batches must be positive')
    output = Path(run_dir)
    state = output / '.job-state'
    cfg = json.loads((state / 'config.json').read_text(encoding='utf8'))
    if cfg['schema_version'] != 2:
        raise ValueError('unsupported checkpoint schema')
    if (output / 'Run_Manifest.json').exists():
        raise FileExistsError('completed job already exists')
    if cfg.get('rules_version') != RULES_VERSION:
        raise ValueError('classification rules version changed or was not recorded; start a new job')
    if file_sha256(Path(cfg['input_path'])) != cfg['input_sha256']:
        raise ValueError('input source changed since checkpoint')
    if file_sha256(Path(cfg['geo_db'])) != cfg['geo_sha256']:
        raise ValueError('geo reference pack changed since checkpoint')
    require_readable_pack(Path(cfg['geo_db']))
    if file_sha256(Path(cfg['hkp_db'])) != cfg['hkp_sha256']:
        raise ValueError('HKP reference catalogue changed since checkpoint')
    approval = _load_approval(
        Path(cfg['approval_manifest_path']) if cfg.get('approval_manifest_path') else None,
        Path(cfg['approval_key_path']) if cfg.get('approval_key_path') else None,
        Path(cfg['hkp_db']))
    if approval is not None and cfg.get('approval_manifest_sha256') \
            and approval.manifest_sha256 != cfg['approval_manifest_sha256']:
        raise ValueError('HKP approval manifest changed since checkpoint')
    if not cfg['allow_unverified_reference_data']:
        if approval is None:
            raise ValueError('a signed HKP approval manifest and key are required')
        if not approval.is_production:
            raise ValueError('the supplied HKP approval cannot authorise production')
    if verify_shards is not None:
        cfg['verify_shards'] = True
    if keep_checkpoint is not None:
        cfg['keep_checkpoint'] = bool(keep_checkpoint)
    return _process(output, cfg, max_batches=max_batches, approval=approval,
                    cancel=cancel, progress=progress)
