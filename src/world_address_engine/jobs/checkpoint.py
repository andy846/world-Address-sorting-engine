"""Atomic, checksummed per-batch checkpoints for crash-safe offline jobs.

Checkpoint shards include recipient details; keep output directories private.
They are immutable. Only fully published, sha256-matching shards can resume.
"""
from dataclasses import asdict
import hashlib
import json
import os
from pathlib import Path
import re
import tempfile
from typing import Iterable, Iterator

from world_address_engine.models import AddressRecord, ClassificationResult

CHUNK_PATTERN = re.compile(r'^(\d{12})-(\d{12})-([0-9a-f]{64})\.jsonl$')
HEADER_KEY = 'checkpoint_header'


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def atomic_json(path: Path, value: dict) -> None:
    path = Path(path)
    fd, tmp_name = tempfile.mkstemp(prefix='.pending-', dir=path.parent)
    try:
        with os.fdopen(fd, 'w', encoding='utf8') as stream:
            json.dump(value, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(tmp_name, path)
    finally:
        Path(tmp_name).unlink(missing_ok=True)


def commit_batch(state_dir: Path, batch: list[tuple[AddressRecord, ClassificationResult]]) -> Path:
    if not batch:
        raise ValueError('empty batch')
    start = batch[0][0].record_no
    end = batch[-1][0].record_no
    if end - start + 1 != len(batch):
        raise ValueError('batch records must be contiguous')
    fd, tmp_name = tempfile.mkstemp(prefix='.pending-', suffix='.jsonl.tmp', dir=state_dir)
    tmp = Path(tmp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf8', newline='\n') as stream:
            previous = _last_digest(state_dir)
            stream.write(json.dumps({HEADER_KEY: {
                'start': start, 'end': end, 'previous': previous,
            }}, ensure_ascii=False, separators=(',', ':')) + '\n')
            for row, result in batch:
                if row.record_no != result.record_no:
                    raise ValueError('result record ID mismatch')
                data = {'record': {
                    'record_no': row.record_no, 'source_file': row.source_file,
                    'source_sheet': row.source_sheet, 'record_id': row.record_id,
                    'fields': dict(row.fields), 'address_text': row.address_text,
                    'country_hint': row.country_hint, 'input_error': row.input_error,
                }, 'result': asdict(result)}
                stream.write(json.dumps(data, ensure_ascii=False, separators=(',', ':')) + '\n')
            stream.flush()
            os.fsync(stream.fileno())
        digest = file_sha256(tmp)
        target = state_dir / f'{start:012d}-{end:012d}-{digest}.jsonl'
        if target.exists():
            raise FileExistsError('batch already committed')
        os.replace(tmp, target)
        return target
    finally:
        tmp.unlink(missing_ok=True)


def committed_shards(state_dir: Path) -> tuple[list[Path], int]:
    shards = sorted(state_dir.glob('*.jsonl'))
    expected = 1
    previous_digest = None
    for shard in shards:
        match = CHUNK_PATTERN.fullmatch(shard.name)
        if not match:
            raise ValueError('invalid committed checkpoint filename')
        start, end, digest = int(match[1]), int(match[2]), match[3]
        if start != expected or end < start:
            raise ValueError('corrupt checkpoint: missing, overlapping or out-of-order shard')
        if file_sha256(shard) != digest:
            raise ValueError('checkpoint checksum mismatch')
        if _header_previous(shard) != previous_digest:
            raise ValueError('checkpoint shard chain broken; the shard set was rewritten')
        expected = end + 1
        previous_digest = digest
    return shards, expected - 1


def _last_digest(state_dir: Path) -> str | None:
    """The digest of the most recent committed shard, for the hash chain."""
    shards = sorted(state_dir.glob('*.jsonl'))
    if not shards:
        return None
    match = CHUNK_PATTERN.fullmatch(shards[-1].name)
    return match.group(3) if match else None


def _header_previous(shard: Path) -> str | None:
    """The previous-shard digest recorded inside the shard's own header."""
    try:
        with shard.open(encoding='utf8') as stream:
            first = stream.readline()
    except OSError:
        return None
    try:
        payload = json.loads(first)
    except ValueError:
        return None
    header = payload.get(HEADER_KEY)
    if not isinstance(header, dict):
        return None
    previous = header.get('previous')
    return previous if isinstance(previous, str) else None


def iter_saved_pairs(shards: Iterable[Path]) -> Iterator[tuple[AddressRecord, ClassificationResult]]:
    previous = 0
    for shard in shards:
        with shard.open(encoding='utf8') as stream:
            for line in stream:
                payload = json.loads(line)
                if HEADER_KEY in payload:
                    continue
                record = AddressRecord(**payload['record'])
                result = ClassificationResult(**payload['result'])
                if record.record_no != previous + 1 or result.record_no != record.record_no:
                    raise ValueError('corrupt checkpoint: record ordering')
                previous += 1
                yield record, result
