"""Content-pinned verification reuse with synthetic packs only."""
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
from threading import Event, local

import pytest

from tests.unit.test_hk_regional_pack import fixture_pack, source_validation_pack
from world_address_engine.data import hk_regional as hk


@pytest.fixture(autouse=True)
def isolated_cache():
    cache = getattr(hk, '_VERIFICATION_CACHE', None)
    if cache is not None:
        cache.clear()
    yield
    if cache is not None:
        cache.clear()


@pytest.fixture
def sql_connections(monkeypatch):
    """Observe real verifier SQL and prove every connection is closed."""
    connect = sqlite3.connect
    observed = []

    class TracedConnection(sqlite3.Connection):
        was_closed = False

        def close(self):
            super().close()
            self.was_closed = True

    def traced_connect(*args, **kwargs):
        if kwargs.get('uri'):
            kwargs['factory'] = TracedConnection
        connection = connect(*args, **kwargs)
        if kwargs.get('uri'):
            statements = []
            connection.set_trace_callback(statements.append)
            observed.append((connection, statements))
        return connection

    monkeypatch.setattr(hk.sqlite3, 'connect', traced_connect)
    yield observed
    for connection, _ in observed:
        assert connection.was_closed, 'verifier left a SQLite handle open'


def write_manifest(db, metadata):
    db.with_name('manifest.json').write_text(json.dumps(metadata), encoding='utf8')


def replace_preserving_mtime(path, contents):
    before = path.stat()
    path.write_bytes(contents)
    os.utime(path, ns=(before.st_atime_ns, before.st_mtime_ns))
    assert path.stat().st_mtime_ns == before.st_mtime_ns


@pytest.mark.parametrize('source_validation', [False, True])
@pytest.mark.parametrize('full', [False, True])
def test_unchanged_pack_skips_all_repeat_sql_and_returns_fresh_metadata(
        tmp_path, sql_connections, source_validation, full):
    factory = source_validation_pack if source_validation else fixture_pack
    db, expected = factory(tmp_path / 'pack')
    first = hk.verify_hk_pack(db, full=full)
    assert first == expected
    first['alias_count_by_language']['en'] = 999
    if source_validation:
        first['source_validation']['feature_count'] = 999
    assert hk.verify_hk_pack(db, full=full) == expected
    assert hk.hk_pack_metadata(db)['db_sha256'] == expected['db_sha256']
    assert len(sql_connections) == 1
    assert any('foreign_key_check' in sql for sql in sql_connections[0][1])


def test_light_verification_requires_one_full_upgrade_and_never_downgrades(tmp_path, sql_connections):
    db, _ = fixture_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db, full=False)
    hk.verify_hk_pack(db, full=False)
    assert len(sql_connections) == 1
    hk.verify_hk_pack(db)  # The default must remain full=True.
    assert len(sql_connections) == 2
    hk.verify_hk_pack(db, full=False)
    hk.verify_hk_pack(db)
    assert len(sql_connections) == 2
    assert sum(sql == 'PRAGMA integrity_check'
               for _, statements in sql_connections for sql in statements) == 1


def test_four_entry_cache_evicts_least_recently_used_path(tmp_path, sql_connections):
    packs = [fixture_pack(tmp_path / str(index))[0] for index in range(5)]
    for db in packs[:4]:
        hk.verify_hk_pack(db)
    hk.verify_hk_pack(packs[0])  # Keep this path; identical bytes elsewhere are distinct keys.
    hk.verify_hk_pack(packs[4])
    hk.verify_hk_pack(packs[0])
    assert len(sql_connections) == 5
    hk.verify_hk_pack(packs[1])
    assert len(sql_connections) == 6


def test_raw_manifest_bytes_are_part_of_cache_identity(tmp_path, sql_connections):
    db, expected = fixture_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    manifest = db.with_name('manifest.json')
    replace_preserving_mtime(manifest, json.dumps(expected, indent=2).encode('utf8'))
    assert hk.verify_hk_pack(db) == expected
    assert len(sql_connections) == 2
    hk.verify_hk_pack(db)
    assert len(sql_connections) == 2


def test_cache_contains_only_content_keys_and_boolean_levels(tmp_path):
    db, _ = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db, full=False)
    key = (str(db.resolve()), hashlib.sha256(db.read_bytes()).hexdigest(),
           hashlib.sha256(db.with_name('manifest.json').read_bytes()).hexdigest())
    assert list(hk._VERIFICATION_CACHE.items()) == [(key, False)]
    hk.verify_hk_pack(db)
    assert list(hk._VERIFICATION_CACHE.items()) == [(key, True)]


def test_cache_hit_rehashes_database_twice_and_quarantine_afterwards(tmp_path, monkeypatch, sql_connections):
    db, _ = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    original = hk._hash
    hashed = []

    def observe(path):
        hashed.append(path)
        return original(path)

    monkeypatch.setattr(hk, '_hash', observe)
    hk.verify_hk_pack(db)
    assert hashed == [db, db, db.with_name('quarantine.jsonl')]
    assert len(sql_connections) == 1


def test_rehashed_quarantine_manifest_requires_new_sql_receipt(tmp_path, sql_connections):
    db, metadata = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    receipt = db.with_name('quarantine.jsonl')
    replace_preserving_mtime(receipt, receipt.read_bytes().replace(b'synthetic', b'different'))
    metadata['source_validation']['quarantine_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    write_manifest(db, metadata)
    assert hk.verify_hk_pack(db) == metadata
    assert len(sql_connections) == 2


@pytest.mark.parametrize('changed', ['db', 'manifest', 'quarantine'])
def test_cache_rejects_changed_bytes_with_restored_mtime(tmp_path, sql_connections, changed):
    db, metadata = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    if changed == 'db':
        replace_preserving_mtime(db, db.read_bytes() + b'changed')
    elif changed == 'manifest':
        metadata['record_count'] = 2
        replace_preserving_mtime(db.with_name('manifest.json'), json.dumps(metadata).encode('utf8'))
    else:
        path = db.with_name('quarantine.jsonl')
        replace_preserving_mtime(path, path.read_bytes().replace(b'synthetic', b'different'))
    with pytest.raises(ValueError):
        hk.verify_hk_pack(db)


def test_rehashed_database_must_run_sql_again(tmp_path, sql_connections):
    db, metadata = fixture_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    before = db.stat()
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute('DROP INDEX hk_alias_anchor')
    os.utime(db, ns=(before.st_atime_ns, before.st_mtime_ns))
    metadata['db_sha256'] = hashlib.sha256(db.read_bytes()).hexdigest()
    write_manifest(db, metadata)
    with pytest.raises(ValueError, match='index'):
        hk.verify_hk_pack(db)
    assert len(sql_connections) == 2


@pytest.mark.parametrize('full,upgrade', [(False, False), (True, False), (True, True)])
def test_source_aba_swap_cannot_cache_sql_receipt_for_different_bytes(tmp_path, monkeypatch, full, upgrade):
    db, metadata = fixture_pack(tmp_path / 'pack')
    if upgrade:
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('CREATE TABLE unused(value TEXT)')
            connection.execute("INSERT INTO unused VALUES('synthetic')")
            page = connection.execute("SELECT rootpage FROM sqlite_master WHERE name='unused'").fetchone()[0]
            page_size = connection.execute('PRAGMA page_size').fetchone()[0]
    valid_bytes = db.read_bytes()
    if upgrade:
        contents = bytearray(valid_bytes)
        contents[(page - 1) * page_size] = 0
        db.write_bytes(contents)
    else:
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('DROP INDEX hk_alias_anchor')
    invalid_bytes = db.read_bytes()
    metadata['db_sha256'] = hashlib.sha256(invalid_bytes).hexdigest()
    write_manifest(db, metadata)
    if upgrade:
        hk.verify_hk_pack(db, full=False)
    connect = sqlite3.connect
    connections = []
    source_hashes = []
    original_hash = hk._hash

    class RestoreSourceOnClose(sqlite3.Connection):
        was_closed = False

        def close(self):
            super().close()
            self.was_closed = True
            db.write_bytes(invalid_bytes)

    def swap_at_connect(*args, **kwargs):
        db.write_bytes(valid_bytes)
        kwargs['factory'] = RestoreSourceOnClose
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    def observe_hash(path):
        digest = original_hash(path)
        if path == db:
            source_hashes.append(digest)
        return digest

    with monkeypatch.context() as patch:
        patch.setattr(hk.sqlite3, 'connect', swap_at_connect)
        patch.setattr(hk, '_hash', observe_hash)
        with pytest.raises(ValueError):
            hk.verify_hk_pack(db, full=full)
    assert source_hashes and set(source_hashes) == {metadata['db_sha256']}
    assert db.read_bytes() == invalid_bytes
    assert connections and all(connection.was_closed for connection in connections)
    assert list(hk._VERIFICATION_CACHE.values()) == ([False] if upgrade else [])
    for _ in range(2):
        with pytest.raises(ValueError):
            hk.verify_hk_pack(db, full=full)


def test_private_snapshot_is_used_only_on_miss_or_integrity_upgrade(tmp_path, monkeypatch, sql_connections):
    db, metadata = fixture_pack(tmp_path / 'pack')
    copyfile, connect = hk.shutil.copyfile, hk.sqlite3.connect
    copies, opened = [], []

    def observe_copy(source, destination, *args, **kwargs):
        assert source == db
        copies.append(Path(destination))
        return copyfile(source, destination, *args, **kwargs)

    def observe_connect(database, *args, **kwargs):
        opened.append(database)
        return connect(database, *args, **kwargs)

    monkeypatch.setattr(hk.shutil, 'copyfile', observe_copy)
    monkeypatch.setattr(hk.sqlite3, 'connect', observe_connect)
    for full in (False, False, True, True, False):
        assert hk.verify_hk_pack(db, full=full) == metadata
    assert len(copies) == 2
    assert copies[0].parent != copies[1].parent
    assert all(path.parent != db.parent for path in copies)
    assert opened == [path.as_uri() + '?mode=ro&immutable=1' for path in copies]
    assert all(not path.parent.exists() for path in copies)
    assert len(sql_connections) == 2


@pytest.mark.parametrize('failure', ['copy_error', 'copy_hash', 'connect', 'sql', 'post_sql_hash', 'final_source'])
def test_private_snapshot_is_checked_and_cleaned_on_errors(tmp_path, monkeypatch, failure):
    db, metadata = fixture_pack(tmp_path / 'pack')
    if failure == 'sql':
        with closing(sqlite3.connect(db)) as connection, connection:
            connection.execute('DROP INDEX hk_alias_anchor')
        metadata['db_sha256'] = hashlib.sha256(db.read_bytes()).hexdigest()
        write_manifest(db, metadata)
    original_bytes = db.read_bytes()
    copyfile, connect = hk.shutil.copyfile, hk.sqlite3.connect
    copies, connections = [], []

    def copy_with_fault(source, destination, *args, **kwargs):
        snapshot = Path(destination)
        copies.append(snapshot)
        result = copyfile(source, destination, *args, **kwargs)
        if failure == 'copy_error':
            raise OSError('synthetic copy failure')
        if failure == 'copy_hash':
            snapshot.write_bytes(snapshot.read_bytes() + b'changed copy')
        return result

    class CloseWithFault(sqlite3.Connection):
        was_closed = False

        def close(self):
            super().close()
            self.was_closed = True
            if failure == 'post_sql_hash' and copies:
                snapshot = copies[-1]
                snapshot.write_bytes(snapshot.read_bytes() + b'changed after SQL')

    def connect_with_fault(*args, **kwargs):
        if failure == 'connect':
            raise sqlite3.OperationalError('synthetic connect failure')
        if failure == 'final_source':
            db.with_name('manifest.json').write_bytes(b'{}')
        kwargs['factory'] = CloseWithFault
        connection = connect(*args, **kwargs)
        connections.append(connection)
        return connection

    monkeypatch.setattr(hk.shutil, 'copyfile', copy_with_fault)
    monkeypatch.setattr(hk.sqlite3, 'connect', connect_with_fault)
    with pytest.raises(ValueError):
        hk.verify_hk_pack(db)
    assert len(copies) == 1
    assert all(not path.parent.exists() for path in copies)
    assert all(connection.was_closed for connection in connections)
    assert db.read_bytes() == original_bytes
    assert not hk._VERIFICATION_CACHE


@pytest.mark.parametrize('mutation', ['extra_metadata', 'duplicate_key', 'duplicate_locator'])
def test_cache_preserves_exact_source_contract_and_duplicate_rejection(tmp_path, mutation):
    db, metadata = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    receipt = db.with_name('quarantine.jsonl')
    if mutation == 'extra_metadata':
        metadata['source_validation']['extra'] = 'forbidden'
    else:
        lines = receipt.read_bytes().splitlines(keepends=True)
        if mutation == 'duplicate_key':
            lines[0] = lines[0].replace(b'{', b'{"reason":"feature_schema",', 1)
        else:
            lines[1] = lines[0]
        receipt.write_bytes(b''.join(lines))
        metadata['source_validation']['quarantine_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    write_manifest(db, metadata)
    with pytest.raises(ValueError):
        hk.verify_hk_pack(db)


def test_cache_hit_still_streams_and_validates_quarantine(tmp_path, monkeypatch, sql_connections):
    db, metadata = source_validation_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    original = hk._verify_source_validation
    validated = []
    read_bytes = Path.read_bytes

    def streaming_only(path):
        assert path.name != 'quarantine.jsonl', 'quarantine must be streamed'
        return read_bytes(path)

    def validate(*args):
        result = original(*args)
        validated.append(result)
        return result

    monkeypatch.setattr(Path, 'read_bytes', streaming_only)
    monkeypatch.setattr(hk, '_verify_source_validation', validate)
    assert hk.verify_hk_pack(db) == metadata
    assert validated == [db.with_name('quarantine.jsonl')]
    assert len(sql_connections) == 1


@pytest.mark.parametrize('suffix', ['-wal', '-journal', 'header'])
def test_cache_rejects_nonstandalone_database(tmp_path, suffix):
    db, metadata = fixture_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    if suffix == 'header':
        contents = bytearray(db.read_bytes())
        contents[18:20] = b'\x02\x02'
        db.write_bytes(contents)
        metadata['db_sha256'] = hashlib.sha256(contents).hexdigest()
        write_manifest(db, metadata)
    else:
        db.with_name(db.name + suffix).touch()
    with pytest.raises(ValueError, match='standalone'):
        hk.verify_hk_pack(db)


@pytest.mark.parametrize('cached', [False, True])
@pytest.mark.parametrize('changed', ['db', 'manifest', 'quarantine', '-wal', '-journal', 'header'])
def test_final_snapshot_checks_run_on_hits_and_misses(tmp_path, monkeypatch, sql_connections, cached, changed):
    db, metadata = source_validation_pack(tmp_path / 'pack')
    if cached:
        hk.verify_hk_pack(db)
    original = hk._standalone_database
    calls = 0

    def mutate_after_initial_check(path):
        nonlocal calls
        original(path)
        calls += 1
        if calls != 1:
            return
        if changed == 'manifest':
            manifest = db.with_name('manifest.json')
            manifest.write_bytes(manifest.read_bytes() + b' ')
        elif changed == 'quarantine':
            receipt = db.with_name('quarantine.jsonl')
            receipt.write_bytes(receipt.read_bytes() + b' ')
        elif changed in ('-wal', '-journal'):
            db.with_name(db.name + changed).touch()
        elif changed == 'header':
            contents = bytearray(db.read_bytes())
            contents[18:20] = b'\x02\x02'
            db.write_bytes(contents)
        else:
            db.write_bytes(db.read_bytes() + b'changed')

    monkeypatch.setattr(hk, '_standalone_database', mutate_after_initial_check)
    with pytest.raises(ValueError, match='changed|standalone'):
        hk.verify_hk_pack(db)
    # A changed source copied on a miss is now rejected before opening SQL.
    expected_connections = 0 if not cached and changed in ('db', 'header') else 1
    assert len(sql_connections) == expected_connections


def test_sql_invalid_pack_is_never_cached(tmp_path, sql_connections):
    db, metadata = fixture_pack(tmp_path / 'pack')
    metadata['alias_count'] = 2
    write_manifest(db, metadata)
    for _ in range(2):
        with pytest.raises(ValueError, match='count'):
            hk.verify_hk_pack(db)
    assert len(sql_connections) == 2


def test_failed_full_integrity_upgrade_is_never_cached(tmp_path, sql_connections):
    db, metadata = fixture_pack(tmp_path / 'pack')
    with closing(sqlite3.connect(db)) as connection, connection:
        connection.execute('CREATE TABLE unused(value TEXT)')
        connection.execute("INSERT INTO unused VALUES('synthetic')")
        page = connection.execute("SELECT rootpage FROM sqlite_master WHERE name='unused'").fetchone()[0]
        page_size = connection.execute('PRAGMA page_size').fetchone()[0]
    contents = bytearray(db.read_bytes())
    contents[(page - 1) * page_size] = 0  # Corrupt only an otherwise unqueried btree page.
    db.write_bytes(contents)
    metadata['db_sha256'] = hashlib.sha256(contents).hexdigest()
    write_manifest(db, metadata)
    hk.verify_hk_pack(db, full=False)
    for _ in range(2):
        with pytest.raises(ValueError):
            hk.verify_hk_pack(db)
    hk.verify_hk_pack(db, full=False)
    assert len(sql_connections) == 3
    assert sum(sql == 'PRAGMA integrity_check'
               for _, statements in sql_connections for sql in statements) == 2


def test_failed_final_check_does_not_cache_snapshot(tmp_path, monkeypatch, sql_connections):
    db, metadata = fixture_pack(tmp_path / 'pack')
    manifest = db.with_name('manifest.json')
    contents = manifest.read_bytes()
    # Mutate before final metadata consumption, regardless of its check ordering.
    standalone = hk._standalone_database

    def mutate_before_sql(path):
        standalone(path)
        manifest.write_bytes(b'{}')

    with monkeypatch.context() as patch:
        patch.setattr(hk, '_standalone_database', mutate_before_sql)
        with pytest.raises(ValueError):
            hk.verify_hk_pack(db)
    manifest.write_bytes(contents)
    assert hk.verify_hk_pack(db) == metadata
    assert len(sql_connections) == 2


def test_new_process_runs_full_integrity_again(tmp_path):
    db, _ = fixture_pack(tmp_path / 'pack')
    hk.verify_hk_pack(db)
    script = '''
import json, sqlite3, sys
from world_address_engine.data.hk_regional import verify_hk_pack
connect = sqlite3.connect
statements = []
def traced(*args, **kwargs):
    db = connect(*args, **kwargs)
    db.set_trace_callback(statements.append)
    return db
sqlite3.connect = traced
verify_hk_pack(sys.argv[1])
verify_hk_pack(sys.argv[1])
print(json.dumps(statements.count('PRAGMA integrity_check')))
'''
    environment = dict(os.environ, PYTHONPATH=str(Path(hk.__file__).resolve().parents[2]),
                       PYTHONDONTWRITEBYTECODE='1')
    result = subprocess.run([sys.executable, '-c', script, str(db)], cwd=tmp_path,
                            env=environment, capture_output=True, text=True, check=True, timeout=20)
    assert json.loads(result.stdout) == 1


@pytest.mark.parametrize('pause_during', ['hash', 'sql'])
def test_concurrent_light_miss_cannot_downgrade_full_result(
        tmp_path, monkeypatch, sql_connections, pause_during):
    db, _ = fixture_pack(tmp_path / 'pack')
    state = local()
    light_waiting, release_light = Event(), Event()
    released = []

    def pause():
        light_waiting.set()
        released.append(release_light.wait(10))

    original_hash = hk._hash

    def pause_light_final_hash(path):
        result = original_hash(path)
        if path == db and getattr(state, 'light', False):
            state.calls = getattr(state, 'calls', 0) + 1
            if state.calls == 2:
                pause()
        return result

    original_connect = hk.sqlite3.connect

    def pause_light_sql(*args, **kwargs):
        connection = original_connect(*args, **kwargs)
        statements = sql_connections[-1][1]

        def trace(sql):
            statements.append(sql)
            if getattr(state, 'light', False) and sql == 'PRAGMA query_only=ON':
                pause()

        connection.set_trace_callback(trace)
        return connection

    def light_verify():
        state.light = True
        return hk.verify_hk_pack(db, full=False)

    if pause_during == 'hash':
        monkeypatch.setattr(hk, '_hash', pause_light_final_hash)
    else:
        monkeypatch.setattr(hk.sqlite3, 'connect', pause_light_sql)
    with ThreadPoolExecutor(max_workers=1) as executor:
        light = executor.submit(light_verify)
        try:
            assert light_waiting.wait(10)
            hk.verify_hk_pack(db)
        finally:
            release_light.set()
        light.result(timeout=10)
    assert released == [True], 'hashing/SQL must not hold the cache lock'
    hk.verify_hk_pack(db)
    assert len(sql_connections) == 2
