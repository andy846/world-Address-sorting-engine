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
