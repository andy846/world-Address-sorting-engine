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
from typing import Iterable, Iterator, NamedTuple

from world_address_engine.models import AddressRecord, ClassificationResult

CHUNK_PATTERN = re.compile(r'^(\d{12})-(\d{12})-([0-9a-f]{64})\.jsonl$')
HEADER_KEY = 'checkpoint_header'


class ShardHeader(NamedTuple):
    start: int
    end: int
    previous: str | None
    rules_version: str


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


def commit_batch(state_dir: Path, batch: list[tuple[AddressRecord, ClassificationResult]],
                 rules_version: str) -> Path:
    if not batch:
        raise ValueError('empty batch')
    if not isinstance(rules_version, str) or not rules_version.strip():
        raise ValueError('a non-empty rules version is required')
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
                'rules_version': rules_version,
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


def committed_shards(state_dir: Path, *,
                     expected_rules_version: str) -> tuple[list[Path], int]:
    if not isinstance(expected_rules_version, str) or not expected_rules_version.strip():
        raise ValueError('a non-empty expected rules version is required')
    shards = sorted(state_dir.glob('*.jsonl'))
    expected = 1
    previous_digest = None
    recorded_rules_version = None
    for shard in shards:
        match = CHUNK_PATTERN.fullmatch(shard.name)
        if not match:
            raise ValueError('invalid committed checkpoint filename')
        start, end, digest = int(match[1]), int(match[2]), match[3]
        if start != expected or end < start:
            raise ValueError('corrupt checkpoint: missing, overlapping or out-of-order shard')
        if file_sha256(shard) != digest:
            raise ValueError('checkpoint checksum mismatch')
        header = _header_metadata(shard)
        if header.start != start or header.end != end:
            raise ValueError(
                'corrupt checkpoint: shard header does not match its filename')
        if header.previous != previous_digest:
            raise ValueError('checkpoint shard chain broken; the shard set was rewritten')
        if header.rules_version != expected_rules_version:
            raise ValueError('checkpoint shard rules version does not match this run')
        if (recorded_rules_version is not None
                and header.rules_version != recorded_rules_version):
            raise ValueError('checkpoint shard rules version changed mid-run')
        recorded_rules_version = header.rules_version
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


def _header_metadata(shard: Path) -> ShardHeader:
    """Parse and validate the first line of a committed shard."""
    try:
        with shard.open(encoding='utf8') as stream:
            first = stream.readline()
    except OSError as exc:
        raise ValueError('corrupt checkpoint: shard header is unreadable') from exc
    try:
        payload = json.loads(first)
    except (TypeError, ValueError) as exc:
        raise ValueError('corrupt checkpoint: shard header is invalid JSON') from exc
    return _header_from_payload(payload)


def _header_from_payload(payload: object) -> ShardHeader:
    if not isinstance(payload, dict):
        raise ValueError('corrupt checkpoint: shard header is invalid')
    header = payload.get(HEADER_KEY)
    if not isinstance(header, dict):
        raise ValueError('corrupt checkpoint: shard header is missing')
    start = header.get('start')
    end = header.get('end')
    previous = header.get('previous')
    rules_version = header.get('rules_version')
    if (not isinstance(start, int) or isinstance(start, bool)
            or not isinstance(end, int) or isinstance(end, bool)
            or start < 1 or end < start):
        raise ValueError('corrupt checkpoint: invalid shard row boundary')
    if previous is not None and (
            not isinstance(previous, str)
            or len(previous) != 64
            or any(character not in '0123456789abcdef' for character in previous)):
        raise ValueError('corrupt checkpoint: invalid previous-shard digest')
    if not isinstance(rules_version, str) or not rules_version.strip():
        raise ValueError('corrupt checkpoint: shard has no rules version')
    return ShardHeader(start, end, previous, rules_version)


def iter_saved_pairs(shards: Iterable[Path]) -> Iterator[tuple[AddressRecord, ClassificationResult]]:
    previous = 0
    for shard in shards:
        match = CHUNK_PATTERN.fullmatch(shard.name)
        if not match:
            raise ValueError('invalid committed checkpoint filename')
        filename_start, filename_end, filename_digest = (
            int(match[1]), int(match[2]), match[3])
        digest = hashlib.sha256()
        header = None
        rows = 0
        try:
            with shard.open('rb') as stream:
                for raw_line in stream:
                    digest.update(raw_line)
                    try:
                        payload = json.loads(raw_line.decode('utf8'))
                    except (UnicodeDecodeError, TypeError, ValueError) as exc:
                        raise ValueError(
                            f'corrupt checkpoint: invalid JSON in {shard.name}') from exc
                    if header is None:
                        header = _header_from_payload(payload)
                        if (header.start != filename_start
                                or header.end != filename_end):
                            raise ValueError(
                                'corrupt checkpoint: shard header does not match '
                                'its filename')
                        if header.start != previous + 1:
                            raise ValueError(
                                'corrupt checkpoint: shard row boundary is not contiguous')
                        continue
                    if HEADER_KEY in payload:
                        raise ValueError(
                            f'corrupt checkpoint: duplicate header in {shard.name}')
                    try:
                        record = AddressRecord(**payload['record'])
                        result = ClassificationResult(**payload['result'])
                    except (KeyError, TypeError, ValueError) as exc:
                        raise ValueError(
                            f'corrupt checkpoint: invalid row in {shard.name}') from exc
                    if record.record_no != previous + 1 or result.record_no != record.record_no:
                        raise ValueError('corrupt checkpoint: record ordering')
                    rows += 1
                    previous += 1
                    yield record, result
        except OSError as exc:
            raise ValueError(f'corrupt checkpoint: cannot read {shard.name}') from exc
        if header is None:
            raise ValueError(f'corrupt checkpoint: empty shard {shard.name}')
        expected_rows = filename_end - filename_start + 1
        if rows != expected_rows or previous != filename_end:
            raise ValueError(
                f'corrupt checkpoint: shard row count does not match its boundary '
                f'in {shard.name}')
        if digest.hexdigest() != filename_digest:
            raise ValueError('checkpoint checksum mismatch')
