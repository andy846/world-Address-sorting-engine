"""Regional pack integrity is distinct from the global GeoNames format."""
import hashlib
import importlib
import json
import sqlite3
from contextlib import closing
from pathlib import Path

import pytest


def api():
    return importlib.import_module('world_address_engine.data.hk_regional')


def fixture_pack(path):
    path.mkdir()
    with closing(sqlite3.connect(path / 'pack.db')) as db, db:
        db.executescript('''
        CREATE TABLE hk_buildings(csu_id TEXT PRIMARY KEY);
        CREATE TABLE hk_addresses(address_id TEXT PRIMARY KEY,csu_id TEXT,source_member TEXT,source_index INTEGER,
          geo_address TEXT,longitude REAL,latitude REAL,region_en TEXT,region_hant TEXT,district_en TEXT,
          district_hant TEXT,number_from TEXT,number_to TEXT,number_conflict INTEGER);
        CREATE TABLE hk_aliases(address_id TEXT,kind TEXT,language TEXT,name TEXT,search_key TEXT,derived INTEGER,
          anchor TEXT,PRIMARY KEY(address_id,kind,language,search_key));
        CREATE INDEX hk_alias_lookup ON hk_aliases(search_key,kind,address_id);
        CREATE INDEX hk_alias_anchor ON hk_aliases(anchor,address_id);
        CREATE INDEX hk_alias_address ON hk_aliases(address_id);
        CREATE TABLE hk_pack_metadata(profile TEXT,schema_version INTEGER,normalization_version INTEGER);
        INSERT INTO hk_pack_metadata VALUES('HK_BILINGUAL_REGIONAL',1,1);
        INSERT INTO hk_buildings VALUES('1234567890T20260101');
        INSERT INTO hk_addresses(address_id,csu_id,source_member,source_index,number_conflict)
          VALUES('address1','1234567890T20260101','fixture.geojson',1,0);
        INSERT INTO hk_aliases VALUES('address1','building','en','Example House','example house',0,'example');
        ''')
    metadata = {'pack_id': 'hk-bilingual-als','profile': 'HK_BILINGUAL_REGIONAL','pack_version': '2026-10-23-r1',
                'schema_version':1,'normalization_version':1,'source_date':'2026-10-23',
                'source_url':'https://www.als.gov.hk/data/ALS-GeoJSON.zip','source_sha256':'a'*64,
                'schema_sha256':'b'*64,'db_sha256':hashlib.sha256((path/'pack.db').read_bytes()).hexdigest(),
                'record_count':1,'building_count':1,'alias_count':1,'alias_count_by_language':{'en':1},
                'conversion_version':'opencc-python-reimplemented==0.1.7',
                'attribution':'Government of the HKSAR / Digital Policy Office / DATA.GOV.HK',
                'license':'https://data.gov.hk/en/terms-and-conditions'}
    (path/'manifest.json').write_text(json.dumps(metadata),encoding='utf8')
    (path/'ATTRIBUTION.txt').write_text(metadata['attribution'],encoding='utf8')
    return path/'pack.db',metadata


@pytest.mark.parametrize('left,right',[("QUEEN’S ROAD, CENTRAL","queen's road central"),
                                      ('觀 塘．道','觀塘道'),('ＡＢＣ—１２','abc 12')])
def test_normalization_is_identical_for_punctuation_width_and_han_spaces(left,right):
    assert api().normalize_hk_key(left)==api().normalize_hk_key(right)


def test_anchor_prefers_content_and_supports_short_chinese():
    assert api().alias_anchor('EXAMPLE INDUSTRIAL BUILDING')=='example'
    assert api().alias_anchor('怡富工業大廈')=='怡富工'
    assert api().alias_anchor('南街')=='南街'


def test_verified_install_is_immutable_and_metadata_pins_files(tmp_path):
    db,metadata=fixture_pack(tmp_path/'stage')
    assert api().verify_hk_pack(db)==metadata
    installed=api().install_hk_pack(db.parent,tmp_path/'packs')
    assert installed.name=='pack.db' and installed.parent.name=='hk-bilingual-als-2026-10-23-r1'
    pinned=api().hk_pack_metadata(installed)
    assert pinned['db_sha256']==metadata['db_sha256']
    assert pinned['path']==str(installed.resolve())
    assert pinned['manifest_sha256']
    with pytest.raises(FileExistsError):api().install_hk_pack(db.parent,tmp_path/'packs')
    api().verify_hk_pack(installed)
    # Every verifier connection must close on Windows as well as Linux.
    moved=installed.with_name('renamed.db');installed.rename(moved);moved.rename(installed)


@pytest.mark.parametrize('change',['hash','profile','count','version','language','index'])
def test_invalid_selected_pack_is_refused(tmp_path,change):
    db,metadata=fixture_pack(tmp_path/'stage')
    if change=='hash':
        with db.open('ab') as f:f.write(b'changed')
    elif change=='profile':metadata['profile']='EXTENDED_GLOBAL'
    elif change=='count':metadata['record_count']=7
    elif change=='version':metadata['schema_version']=2
    elif change=='language':metadata['alias_count_by_language']={'en':2}
    elif change=='index':
        with closing(sqlite3.connect(db)) as con, con:con.execute('DROP INDEX hk_alias_anchor')
        metadata['db_sha256']=hashlib.sha256(db.read_bytes()).hexdigest()
    (db.parent/'manifest.json').write_text(json.dumps(metadata),encoding='utf8')
    with pytest.raises(ValueError):api().verify_hk_pack(db)


def rehash_manifest(db, metadata):
    metadata['db_sha256'] = hashlib.sha256(db.read_bytes()).hexdigest()
    (db.parent / 'manifest.json').write_text(json.dumps(metadata), encoding='utf8')


@pytest.mark.parametrize('mutation', ['column', 'orphan', 'partial_index', 'null_provenance', 'primary_key'])
def test_verified_pack_requires_query_schema_references_and_full_indexes(tmp_path, mutation):
    db, metadata = fixture_pack(tmp_path / 'stage')
    with closing(sqlite3.connect(db)) as con, con:
        if mutation == 'column':
            con.execute('ALTER TABLE hk_addresses RENAME COLUMN number_from TO unexpected')
        elif mutation == 'orphan':
            con.execute("UPDATE hk_aliases SET address_id='missing'")
        elif mutation == 'partial_index':
            con.execute('DROP INDEX hk_alias_anchor')
            con.execute("CREATE INDEX hk_alias_anchor ON hk_aliases(anchor,address_id) WHERE kind='building'")
        elif mutation == 'null_provenance':
            con.execute('UPDATE hk_addresses SET source_member=NULL')
        else:
            con.executescript('ALTER TABLE hk_addresses RENAME TO old_addresses; '
                              'CREATE TABLE hk_addresses AS SELECT * FROM old_addresses; '
                              'DROP TABLE old_addresses;')
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)


def test_wal_backed_changes_cannot_bypass_the_pinned_database_hash(tmp_path):
    db, metadata = fixture_pack(tmp_path / 'stage')
    with closing(sqlite3.connect(db)) as con:
        con.execute('PRAGMA journal_mode=WAL')
        con.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        rehash_manifest(db, metadata)
        con.execute("UPDATE hk_aliases SET name='changed outside main database'")
        con.commit()
        assert metadata['db_sha256'] == hashlib.sha256(db.read_bytes()).hexdigest()
        with pytest.raises(ValueError, match='standalone|journal|WAL'):
            api().hk_pack_metadata(db)


def test_installation_rejects_a_different_verified_snapshot_during_copy(tmp_path, monkeypatch):
    import shutil
    db, metadata = fixture_pack(tmp_path / 'stage')
    original_copy = shutil.copy2
    changed = False
    def replace_source(source, target):
        nonlocal changed
        if not changed:
            changed = True
            with closing(sqlite3.connect(db)) as con, con:
                con.execute("UPDATE hk_aliases SET name='changed source'")
            rehash_manifest(db, metadata)
        return original_copy(source, target)
    monkeypatch.setattr(api().shutil, 'copy2', replace_source)
    active = tmp_path / 'packs'
    with pytest.raises(ValueError, match='changed|snapshot'):
        api().install_hk_pack(db.parent, active)
    assert not list(active.glob('hk-bilingual-*'))


def source_validation_pack(path, *, policy='quarantine-invalid', entries=None):
    """One installed address from two valid source features, plus exclusions."""
    db, metadata = fixture_pack(path)
    if entries is None:
        entries = [{'source_member': 'synthetic.geojson', 'source_index': 3,
                    'reason': 'feature_schema'},
                   {'source_member': 'synthetic.geojson', 'source_index': 4,
                    'reason': 'invalid_hk_address'}]
    contents = ''.join(json.dumps(entry) + '\n' for entry in entries).encode('utf8')
    validation = {'policy': policy, 'coverage': 'partial' if entries else 'complete',
                  'feature_count': 2 + len(entries), 'valid_feature_count': 2,
                  'quarantined_feature_count': len(entries),
                  'quarantine_file': None, 'quarantine_sha256': None}
    if policy == 'quarantine-invalid':
        (db.parent / 'quarantine.jsonl').write_bytes(contents)
        validation.update(quarantine_file='quarantine.jsonl',
                          quarantine_sha256=hashlib.sha256(contents).hexdigest())
    metadata['source_validation'] = validation
    rehash_manifest(db, metadata)
    return db, metadata


@pytest.mark.parametrize('policy,entries', [('strict', []), ('quarantine-invalid', []),
                                          ('quarantine-invalid', None)])
def test_source_validation_is_verified_and_pinned(tmp_path, policy, entries):
    db, metadata = source_validation_pack(tmp_path / 'stage', policy=policy, entries=entries)
    assert api().verify_hk_pack(db) == metadata
    assert api().hk_pack_metadata(db)['source_validation'] == metadata['source_validation']


def test_legacy_metadata_does_not_gain_source_validation(tmp_path):
    db, _ = fixture_pack(tmp_path / 'legacy')
    assert 'source_validation' not in api().hk_pack_metadata(db)


@pytest.mark.parametrize('validation', [None, [], 'partial', 1, True])
def test_source_validation_requires_an_object(tmp_path, validation):
    db, metadata = fixture_pack(tmp_path / 'stage')
    metadata['source_validation'] = validation
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db, full=False)


@pytest.mark.parametrize('missing', ['policy', 'coverage', 'feature_count', 'valid_feature_count',
                                    'quarantined_feature_count', 'quarantine_file', 'quarantine_sha256'])
def test_source_validation_requires_every_field(tmp_path, missing):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    del metadata['source_validation'][missing]
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)


@pytest.mark.parametrize('key,value', [
    ('policy', 'ignore-invalid'), ('policy', None), ('policy', []),
    ('coverage', 'unknown'), ('coverage', None), ('coverage', {}),
    ('coverage', 'complete'), ('feature_count', 3),
    ('quarantine_file', '../quarantine.jsonl'), ('quarantine_file', './quarantine.jsonl'),
    ('quarantine_file', 'other.jsonl'), ('quarantine_file', '/quarantine.jsonl'),
    ('quarantine_file', 'C:\\quarantine.jsonl'), ('quarantine_file', None),
    ('quarantine_sha256', None), ('quarantine_sha256', 'A' * 64),
    ('quarantine_sha256', 'g' * 64), ('quarantine_sha256', 'a' * 63),
    ('quarantine_sha256', 123),
])
def test_source_validation_rejects_bad_metadata(tmp_path, key, value):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    metadata['source_validation'][key] = value
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().hk_pack_metadata(db)


@pytest.mark.parametrize('key', ['feature_count', 'valid_feature_count', 'quarantined_feature_count'])
@pytest.mark.parametrize('value', [True, 1.0, '1', -1, None])
def test_source_validation_counts_are_nonnegative_integers(tmp_path, key, value):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    metadata['source_validation'][key] = value
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)


@pytest.mark.parametrize('mutation', ['partial_without_exclusions', 'strict_exclusions',
                                      'strict_file', 'strict_hash', 'record_count_exceeds_valid'])
def test_source_validation_enforces_policy_coverage_and_source_totals(tmp_path, mutation):
    db, metadata = source_validation_pack(tmp_path / 'stage', policy='strict', entries=[])
    validation = metadata['source_validation']
    if mutation == 'partial_without_exclusions':
        validation['coverage'] = 'partial'
    elif mutation == 'strict_exclusions':
        validation.update(coverage='partial', feature_count=3, quarantined_feature_count=1)
    elif mutation == 'strict_file':
        validation['quarantine_file'] = 'quarantine.jsonl'
    elif mutation == 'strict_hash':
        validation['quarantine_sha256'] = 'a' * 64
    else:
        validation.update(feature_count=0, valid_feature_count=0)
    rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)


@pytest.mark.parametrize('mutation', ['missing', 'checksum', 'fewer_lines', 'more_lines',
                                      'invalid_json', 'blank_line', 'invalid_utf8'])
def test_quarantine_file_must_match_hash_count_and_jsonl(tmp_path, mutation):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    sidecar = db.parent / 'quarantine.jsonl'
    if mutation == 'missing':
        sidecar.unlink()
    elif mutation == 'checksum':
        sidecar.write_bytes(sidecar.read_bytes() + b' ')
    else:
        contents = sidecar.read_bytes()
        contents = {'fewer_lines': contents.splitlines(keepends=True)[0],
                    'more_lines': contents + contents,
                    'invalid_json': b'{broken\n', 'blank_line': contents + b'\n',
                    'invalid_utf8': b'\xff\n'}[mutation]
        sidecar.write_bytes(contents)
        metadata['source_validation']['quarantine_sha256'] = hashlib.sha256(contents).hexdigest()
        rehash_manifest(db, metadata)
    with pytest.raises(ValueError):
        api().verify_hk_pack(db, full=False)


@pytest.mark.parametrize('entry', [None, [], {},
    {'source_member': 1, 'source_index': 1, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': True, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': 0, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': -1, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': 1.0, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': '1', 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': 1, 'reason': 'other'},
    {'source_member': 'fixture', 'source_index': 1, 'reason': []},
    {'source_member': 'fixture', 'source_index': 1},
    {'source_index': 1, 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'reason': 'feature_schema'},
    {'source_member': 'fixture', 'source_index': 1, 'reason': 'feature_schema', 'extra': 'unexpected'},
])
def test_quarantine_entries_require_source_location_and_allowed_reason(tmp_path, entry):
    db, _ = source_validation_pack(tmp_path / 'stage', entries=[entry])
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)


def test_quarantine_verification_streams_instead_of_loading_the_whole_file(tmp_path, monkeypatch):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    read_bytes, read_text = Path.read_bytes, Path.read_text

    def bounded_read(original):
        def read(path, *args, **kwargs):
            assert path.name != 'quarantine.jsonl', 'quarantine must be streamed'
            return original(path, *args, **kwargs)
        return read

    monkeypatch.setattr(Path, 'read_bytes', bounded_read(read_bytes))
    monkeypatch.setattr(Path, 'read_text', bounded_read(read_text))
    assert api().hk_pack_metadata(db)['source_validation'] == metadata['source_validation']


def test_quarantine_file_is_rechecked_after_database_verification(tmp_path, monkeypatch):
    db, _ = source_validation_pack(tmp_path / 'stage')
    original_hash = api()._hash
    db_hashes = 0

    def mutate_after_consumption(path):
        nonlocal db_hashes
        if Path(path) == db:
            db_hashes += 1
            if db_hashes == 2:
                (db.parent / 'quarantine.jsonl').write_bytes(b'changed during verification\n')
        return original_hash(path)

    monkeypatch.setattr(api(), '_hash', mutate_after_consumption)
    with pytest.raises(ValueError, match='changed|checksum'):
        api().verify_hk_pack(db)


@pytest.mark.parametrize('policy,entries', [('strict', []), ('quarantine-invalid', []),
                                          ('quarantine-invalid', None), ('legacy', [])])
def test_install_copies_quarantine_only_when_required_and_verifies_it(tmp_path, policy, entries):
    if policy == 'legacy':
        db, metadata = fixture_pack(tmp_path / 'stage')
    else:
        db, metadata = source_validation_pack(tmp_path / 'stage', policy=policy, entries=entries)
    required = policy == 'quarantine-invalid'
    sidecar = db.parent / 'quarantine.jsonl'
    if not required:
        sidecar.write_text('unreferenced file is not part of the pack', encoding='utf8')
    installed = api().install_hk_pack(db.parent, tmp_path / 'packs')
    copied = installed.parent / 'quarantine.jsonl'
    assert copied.exists() == required
    if required:
        assert copied.read_bytes() == sidecar.read_bytes()
    assert api().verify_hk_pack(installed) == metadata


def test_install_refuses_corrupted_quarantine_copy_and_cleans_temporary_pack(tmp_path, monkeypatch):
    db, _ = source_validation_pack(tmp_path / 'stage')
    original_copy = api().shutil.copy2

    def corrupt_copy(source, target):
        result = original_copy(source, target)
        if Path(source).name == 'quarantine.jsonl':
            Path(target).write_bytes(b'corrupt\n')
        return result

    monkeypatch.setattr(api().shutil, 'copy2', corrupt_copy)
    active = tmp_path / 'packs'
    with pytest.raises(ValueError):
        api().install_hk_pack(db.parent, active)
    assert not list(active.iterdir())


@pytest.mark.parametrize('mutation', ['extra_metadata', 'duplicate_key', 'duplicate_locator'])
def test_partial_receipt_has_exact_contract_and_distinct_feature_locators(tmp_path, mutation):
    db, metadata = source_validation_pack(tmp_path / 'stage')
    validation = metadata['source_validation']
    receipt = db.with_name('quarantine.jsonl')
    if mutation == 'extra_metadata':
        validation['unexpected_raw'] = 'not part of this contract'
    elif mutation == 'duplicate_key':
        tail = receipt.read_bytes().splitlines()[1] + b'\n'
        receipt.write_bytes(b'{"source_member":"hidden value","source_member":"synthetic.geojson",'
                            b'"source_index":3,"reason":"feature_schema"}\n' + tail)
        validation['quarantine_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    else:
        first = receipt.read_bytes().splitlines()[0] + b'\n'
        receipt.write_bytes(first + first)
        validation['quarantined_feature_count'] = 2
        validation['feature_count'] = validation['valid_feature_count'] + 2
        validation['quarantine_sha256'] = hashlib.sha256(receipt.read_bytes()).hexdigest()
    db.with_name('manifest.json').write_text(json.dumps(metadata), encoding='utf8')
    with pytest.raises(ValueError):
        api().verify_hk_pack(db)
