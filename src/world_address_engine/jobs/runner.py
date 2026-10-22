"""Offline streaming classifier with version-pinned, resumable output shards.

This is a TEST-ONLY pipeline until an independently reviewed HKP master is
integrated. It refuses a production run in the current catalogue schema.
"""
from pathlib import Path
import json

from world_address_engine.io.delimited import iter_csv_records, iter_txt_records
from world_address_engine.io.reports import write_reports
from world_address_engine.io.xlsx import iter_xlsx_records
from world_address_engine.matching.classify import classify_record
from world_address_engine.sqlite_util import open_db
from world_address_engine.jobs.checkpoint import (
    atomic_json, commit_batch, committed_shards, file_sha256, iter_saved_pairs,
)


def _hkp_audited(db_path: Path) -> bool:
    """Fail closed for older and fixture catalogues lacking audit approval."""
    with open_db(db_path) as con:
        cols = {row[1] for row in con.execute('PRAGMA table_info(metadata)')}
        if 'production_approved' not in cols:
            return False
        row = con.execute('SELECT production_approved FROM metadata').fetchone()
        return bool(row and row[0] == 1)


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
              testing: bool) -> dict:
    for p in (input_path, geo_db, hkp_db):
        if not p.is_file():
            raise FileNotFoundError(p)
    if batch_size < 1 or batch_size > 100_000:
        raise ValueError('batch_size must be 1 to 100000')
    if not testing and not _hkp_audited(hkp_db):
        raise ValueError('HKP master not production approved; unverified reference data refused')
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
        'schema_version': 1,
    }


def _process(output_dir: Path, cfg: dict, *, max_batches: int | None = None) -> dict:
    state = output_dir / '.job-state'
    paths, last_committed = committed_shards(state)
    source = Path(cfg['input_path'])
    geo = Path(cfg['geo_db'])
    hkp = Path(cfg['hkp_db'])
    iterator = _records(source, cfg['input_options'])
    batch = []
    committed_new = 0
    for record in iterator:
        if record.record_no <= last_committed:
            continue
        if record.record_no != last_committed + len(batch) + 1:
            raise ValueError('nonsequential source record')
        result = classify_record(record, geo, hkp)
        batch.append((record, result))
        if len(batch) >= cfg['batch_size']:
            commit_batch(state, batch)
            last_committed = batch[-1][0].record_no
            batch.clear()
            committed_new += 1
            if max_batches is not None and committed_new >= max_batches:
                return {'run_status':'PAUSED', 'committed_records': last_committed}
    if batch:
        commit_batch(state, batch)
    paths, last_committed = committed_shards(state)
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
    manifest_meta = {
        'production_approved': not cfg['allow_unverified_reference_data'],
        'data_approval': 'TEST_ONLY_UNVERIFIED' if cfg['allow_unverified_reference_data'] else 'INDEPENDENTLY_AUDITED',
        'input_sha256': cfg['input_sha256'],
        'geo_sha256': cfg['geo_sha256'],
        'hkp_sha256': cfg['hkp_sha256'],
        'batch_size': cfg['batch_size'],
    }
    counts = write_reports(iter_saved_pairs(paths), output_dir, manifest_meta)
    return counts


def run_job(input_path: Path, output_dir: Path, geo_db: Path, hkp_db: Path,
            input_options: dict, batch_size: int = 10_000, *,
            max_batches: int | None = None,
            allow_unverified_reference_data: bool = False) -> dict:
    """Start a new offline job. Explicit testing bypass leaves TEST_ONLY manifest."""
    input_path, output_dir, geo_db, hkp_db = map(Path, (input_path, output_dir, geo_db, hkp_db))
    if max_batches is not None and max_batches < 1:
        raise ValueError('max_batches must be positive')
    options = dict(input_options)
    # Validate before creating state; never issue an approved mailing export
    # against merely syntactically validated, unofficial fixture code tables.
    cfg = _snapshot(input_path, geo_db, hkp_db, options, batch_size,
                    allow_unverified_reference_data)
    state = output_dir / '.job-state'
    if state.exists() or output_dir.joinpath('Run_Manifest.json').exists():
        raise FileExistsError('existing job; use resume_job or a new output directory')
    output_dir.mkdir(parents=True, exist_ok=True)
    state.mkdir()
    atomic_json(state / 'config.json', cfg)
    return _process(output_dir, cfg, max_batches=max_batches)


def resume_job(run_dir: Path, *, max_batches: int | None = None) -> dict:
    """Resume a paused/failed job ONLY if all source versions still match."""
    if max_batches is not None and max_batches < 1:
        raise ValueError('max_batches must be positive')
    output = Path(run_dir)
    state = output / '.job-state'
    cfg = json.loads((state / 'config.json').read_text(encoding='utf8'))
    if cfg['schema_version'] != 1:
        raise ValueError('unsupported checkpoint schema')
    if (output / 'Run_Manifest.json').exists():
        raise FileExistsError('completed job already exists')
    if file_sha256(Path(cfg['input_path'])) != cfg['input_sha256']:
        raise ValueError('input source changed since checkpoint')
    if file_sha256(Path(cfg['geo_db'])) != cfg['geo_sha256']:
        raise ValueError('geo reference pack changed since checkpoint')
    if file_sha256(Path(cfg['hkp_db'])) != cfg['hkp_sha256']:
        raise ValueError('HKP reference catalogue changed since checkpoint')
    if not cfg['allow_unverified_reference_data'] and not _hkp_audited(Path(cfg['hkp_db'])):
        raise ValueError('HKP master not production approved')
    return _process(output, cfg, max_batches=max_batches)
