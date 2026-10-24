"""Synthetic ALS schema fixtures; no customer or purported real addresses."""
import gc
import hashlib
import importlib.util
import json
import sqlite3
import weakref
from contextlib import closing
from dataclasses import FrozenInstanceError

import pytest

from tests.unit.test_country_inference import catalogue, record
from tests.unit.test_retrieve import geo


def test_regional_matcher_is_available():
    assert importlib.util.find_spec('world_address_engine.matching.hk_regional') is not None


def make_pack(tmp_path, *, count=1, conflict=0, separate=False):
    from world_address_engine.data.hk_regional import normalize_hk_key, alias_anchor
    root = tmp_path / 'regional'
    root.mkdir(exist_ok=True)
    path = root / 'pack.db'
    with closing(sqlite3.connect(path)) as db, db:
        db.executescript('''
        CREATE TABLE hk_buildings(csu_id TEXT PRIMARY KEY);
        CREATE TABLE hk_addresses(address_id TEXT PRIMARY KEY,csu_id TEXT NOT NULL,
          source_member TEXT NOT NULL,source_index INTEGER NOT NULL,geo_address TEXT,
          longitude REAL,latitude REAL,region_en TEXT,region_hant TEXT,district_en TEXT,
          district_hant TEXT,number_from TEXT,number_to TEXT,number_conflict INTEGER NOT NULL,
          FOREIGN KEY(csu_id) REFERENCES hk_buildings(csu_id));
        CREATE TABLE hk_aliases(address_id TEXT,kind TEXT,language TEXT,name TEXT,
          search_key TEXT,derived INTEGER,anchor TEXT,
          PRIMARY KEY(address_id,kind,language,search_key),
          FOREIGN KEY(address_id) REFERENCES hk_addresses(address_id));
        CREATE INDEX hk_alias_lookup ON hk_aliases(search_key,kind,address_id);
        CREATE INDEX hk_alias_anchor ON hk_aliases(anchor,address_id);
        CREATE INDEX hk_alias_address ON hk_aliases(address_id);
        CREATE TABLE hk_pack_metadata(profile TEXT,schema_version INTEGER,normalization_version INTEGER);
        INSERT INTO hk_pack_metadata VALUES ('HK_BILINGUAL_REGIONAL',1,1);
        INSERT INTO hk_buildings VALUES ('SYNTHETIC-CSU');
        ''')
        aliases = [
            ('building', 'en', 'Lantern Building'),
            ('building', 'zh-Hant', '燈籠大廈'), ('building', 'zh-Hans', '灯笼大厦'),
            ('street', 'en', 'Orchid Road'), ('street', 'zh-Hant', '蘭花路'),
            ('street', 'zh-Hans', '兰花路'),
            ('district', 'en', 'Copper District'), ('district', 'zh-Hant', '銅石區'),
            ('district', 'zh-Hans', '铜石区'),
        ]
        for i in range(count):
            address_id = f'synthetic-{i:03}'
            db.execute('INSERT INTO hk_addresses VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (address_id, 'SYNTHETIC-CSU', 'fixture.geojson', i, None,
                        114.1, 22.3, None, None, 'Copper District', '銅石區', '10', '20', conflict))
            for kind, lang, name in aliases:
                if separate and ((i == 0 and kind != 'building') or (i == 1 and kind == 'building')):
                    continue
                key = normalize_hk_key(name)
                db.execute('INSERT INTO hk_aliases VALUES (?,?,?,?,?,?,?)',
                           (address_id, kind, lang, name, key, int(lang == 'zh-Hans'), alias_anchor(key)))
        totals = dict(db.execute('SELECT language,count(*) FROM hk_aliases GROUP BY language'))
    manifest = dict(profile='HK_BILINGUAL_REGIONAL', schema_version=1, normalization_version=1,
                    pack_id='hk-bilingual-als', pack_version='synthetic-1', source_date='2026-10-24',
                    source_url='https://www.als.gov.hk/', source_sha256='0'*64, schema_sha256='1'*64,
                    db_sha256=hashlib.sha256(path.read_bytes()).hexdigest(), record_count=count,
                    building_count=1, alias_count=sum(totals.values()), alias_count_by_language=totals,
                    conversion_version='opencc-python-reimplemented==0.1.7',
                    attribution='Synthetic test fixture', license_url='https://data.gov.hk/en/terms-and-conditions',
                    license='Synthetic test fixture')
    (root / 'manifest.json').write_text(json.dumps(manifest), encoding='utf8')
    return path


@pytest.mark.parametrize('text', [
    'Lantern Building\n12 Orchid Road',
    '燈籠大廈\n蘭花路十二號',
    '灯笼大厦\n兰花路12号',
    'Lantern Building\n蘭花路12號',
    '燈籠大廈\n12 Orchid Road',
    '12 Orchid Road\nCopper District',
    '蘭花路十二號\n銅石區',
    '兰花路12号\n铜石区',
    'Lantern Building\nOrchid Road',
    'Flat 999\nLantern Building\n12 Orchid Road',
    'Lantern Building\n１２－１４ Orchid Road',
])
def test_same_address_support_matches_in_four_language_forms(tmp_path, text):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path)) as matcher:
        match = matcher.match(text)
        assert match.address_ids == ('synthetic-000',)
        assert match.evidence
        with pytest.raises((FrozenInstanceError, AttributeError)):
            match.address_ids = ()


@pytest.mark.parametrize('text', [
    'Lantern Building', '12 Orchid Road', 'Orchid Road\nCopper District',
    'Lantern Building\n99 Orchid Road', '燈籠大廈\n蘭花路九十九號',
    'Lantern Building\n12 Wrong Road', 'Xlantern Building\n12 Orchid Road',
    'Lantern Buildingette\n12 Orchid Road',
    'Lantern Building\n12 Orchid Roadway',
    'Orchid Road\n蘭花路\n兰花路',
    'Lantern Building\nOrchid Road 99',
    'Lantern Building\n蘭花路99',
    'Lantern Building\n99-12 Orchid Road',
    'Lantern Building\n9-12 Orchid Road',
    'Lantern Building\n蘭花路12至99號',
    'Lantern Building Road\n12 Orchid Road',
    'Lantern Building\n12 Orchid Road Building',
    '燈籠大廈街\n蘭花路12號',
    '燈籠大廈\n蘭花路大廈',
    'Élantern Building\n12 Orchid Road',
    'Lantern Buildingé\n12 Orchid Road',
    'Lantern Building\n９９－１２ Orchid Road',
])
def test_inadequate_or_contradictory_support_does_not_match(tmp_path, text):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path)) as matcher:
        assert matcher.match(text) is None


def repin(path):
    manifest_path = path.with_name('manifest.json')
    metadata = json.loads(manifest_path.read_text(encoding='utf8'))
    with closing(sqlite3.connect(path)) as db:
        metadata['alias_count_by_language'] = dict(db.execute(
            'SELECT language,count(*) FROM hk_aliases GROUP BY language'))
        metadata['alias_count'] = sum(metadata['alias_count_by_language'].values())
    metadata['db_sha256'] = hashlib.sha256(path.read_bytes()).hexdigest()
    manifest_path.write_text(json.dumps(metadata), encoding='utf8')


def test_one_alias_cannot_supply_two_component_roles(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    path = make_pack(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM hk_aliases WHERE kind='building'")
        db.execute("INSERT INTO hk_aliases SELECT address_id,'building',language,name,search_key,derived,anchor "
                   "FROM hk_aliases WHERE kind='street'")
    repin(path)
    with HKRegionalMatcher(path) as matcher:
        assert matcher.match('Orchid Road') is None


def test_selective_anchor_survives_an_overbroad_street_anchor(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    path = make_pack(tmp_path, count=65)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute("DELETE FROM hk_aliases WHERE kind='building' AND address_id != 'synthetic-000'")
    repin(path)
    with HKRegionalMatcher(path) as matcher:
        assert matcher.match('Lantern Building\n12 Orchid Road').address_ids == ('synthetic-000',)


def test_same_building_id_does_not_join_separate_addresses(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path, count=2, separate=True)) as matcher:
        assert matcher.match('Lantern Building\nOrchid Road') is None


def test_conflicting_source_numbers_cannot_supply_number_evidence(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path, conflict=1)) as matcher:
        assert matcher.match('12 Orchid Road\nCopper District') is None
        assert matcher.match('Lantern Building\n12 Orchid Road') is None
        assert matcher.match('Lantern Building\nOrchid Road') is not None


def test_overbroad_anchors_fail_closed(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path, count=65)) as matcher:
        assert matcher.match('Lantern Building\n12 Orchid Road') is None


def test_oversized_numeric_tokens_are_rejected_without_integer_conversion_error(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path)) as matcher:
        assert matcher.match('Lantern Building\n' + '9' * 5000 + ' Orchid Road') is None


def test_capacity_boundary_and_read_only_lifetime(tmp_path):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    path = make_pack(tmp_path, count=64)
    original = path.read_bytes()
    matcher = HKRegionalMatcher(path)
    match = matcher.match('Lantern Building\n12 Orchid Road')
    assert len(match.address_ids) == 64
    connection = matcher._db
    with pytest.raises(sqlite3.OperationalError):
        connection.execute("DELETE FROM hk_aliases")
    matcher.close()
    matcher.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    assert path.read_bytes() == original
    ref = weakref.ref(matcher)
    enabled = gc.isenabled()
    gc.disable()
    try:
        del matcher
        assert ref() is None
    finally:
        if enabled:
            gc.enable()


def test_country_fallback_only_upgrades_eligible_unresolved(tmp_path):
    from world_address_engine.matching.country import CountryClassifier
    pack = make_pack(tmp_path)
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=pack) as classifier:
        result = classifier.classify(record('Example Person\nLantern Building\n12 Orchid Road'))
        assert (result.country_code, result.status, result.reason) == (
            'HK', 'INFERRED', 'HK_REGIONAL_ADDRESS_MATCH')
        assert result.evidence == ('HK_ALS:synthetic-000',)
        assert classifier.classify(record('12 Orchid Road\nJapan')).country_code == 'JP'


@pytest.mark.parametrize('text', [
    'Lantern Building\n12 Orchid Road',
    '燈籠大廈\n蘭花路十二號',
    '灯笼大厦\n兰花路12号',
    'Lantern Building\n蘭花路12號',
])
def test_first_line_typed_building_is_address_context(tmp_path, text):
    from world_address_engine.matching.country import CountryClassifier
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=make_pack(tmp_path)) as classifier:
        assert classifier.classify(record(text)).reason == 'HK_REGIONAL_ADDRESS_MATCH'


def test_country_fallback_can_resolve_incidental_city_homonyms(tmp_path):
    from world_address_engine.matching.country import CountryClassifier
    global_db, regional = geo(tmp_path), make_pack(tmp_path)
    text = 'Example Person\nLantern Building\n12 Orchid Road\nSpringfield'
    with CountryClassifier(global_db, catalogue()) as baseline:
        assert baseline.classify(record(text)).reason == 'MULTIPLE_PLAUSIBLE_COUNTRIES'
    with CountryClassifier(global_db, catalogue(), hk_regional_db=regional) as classifier:
        assert classifier.classify(record(text)).country_code == 'HK'


def test_optional_pack_never_flips_assigned_or_other_unresolved_results(tmp_path):
    from world_address_engine.matching.country import CountryClassifier
    global_db, regional = geo(tmp_path), make_pack(tmp_path)
    texts = ['Example Person\nLantern Building\n12 Orchid Road\nTokyo',
             'Lantern Building\n12 Orchid Road\nJapan',
             'Lantern Building\n12 Orchid Road\nGuangdong',
             '', 'returned mail unknown address', 'Lantern Building',
             'Lantern Building\n12 Orchid Road\nChina\nJapan',
             'Lantern Building\n12 Orchid Road\nGuangdong\nKowloon']
    with CountryClassifier(global_db, catalogue()) as baseline, CountryClassifier(
            global_db, catalogue(), hk_regional_db=regional) as classifier:
        for text in texts:
            assert classifier.classify(record(text)) == baseline.classify(record(text))


def test_classifier_lazily_opens_and_closes_regional_handle(tmp_path):
    from world_address_engine.matching.country import CountryClassifier
    global_db, regional = geo(tmp_path), make_pack(tmp_path)
    classifier = CountryClassifier(global_db, catalogue(), hk_regional_db=regional)
    classifier.classify(record('Japan'))
    assert classifier._hk_regional is None
    classifier.classify(record('Example Person\nLantern Building\n12 Orchid Road'))
    connection = classifier._hk_regional._db
    classifier.close()
    with pytest.raises(sqlite3.ProgrammingError):
        connection.execute('SELECT 1')
    classifier.close()
    enabled = gc.isenabled()
    gc.disable()
    try:
        for _ in range(30):
            with CountryClassifier(global_db, catalogue(), hk_regional_db=regional) as item:
                item.classify(record('Example Person\nLantern Building\n12 Orchid Road'))
            ref = weakref.ref(item)
            del item
            assert ref() is None
    finally:
        if enabled:
            gc.enable()


@pytest.mark.parametrize('prefix,suffix', [
    ('Lantern Building Company\n', ''), ('Mr Lantern Building\n', ''),
    ('Lantern Building\n', '\nChina\nJapan'),
    ('Lantern Building\n', '\nGuangdong\nKowloon'),
    ('Lantern Building\n', '\nTokyo\nLondon'),
])
def test_country_fallback_preserves_roles_and_conflicts(tmp_path, prefix, suffix):
    from world_address_engine.matching.country import CountryClassifier
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=make_pack(tmp_path)) as classifier:
        result = classifier.classify(record(prefix + '12 Orchid Road' + suffix))
        assert result.country_code is None


def test_selected_invalid_pack_raises_at_classifier_construction(tmp_path):
    from world_address_engine.matching.country import CountryClassifier
    bad = tmp_path / 'bad.db'
    bad.write_bytes(b'not sqlite')
    with pytest.raises((ValueError, sqlite3.DatabaseError, FileNotFoundError)):
        CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=bad)


@pytest.mark.parametrize('tail', [
    'Tokyo, London', 'Ontario\nIllinois', 'Tokyo 100-0001\nMumbai 400001',
])
def test_regional_fallback_preserves_foreign_city_and_admin_conflicts(tmp_path, tail):
    from world_address_engine.matching.country import CountryClassifier
    text = 'Example Person\nLantern Building\n12 Orchid Road\n' + tail
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=make_pack(tmp_path)) as classifier:
        result = classifier.classify(record(text))
        assert result.country_code is None
        assert result.reason == 'CONFLICTING_GEOGRAPHIC_CONTEXT'


@pytest.mark.parametrize('street', [
    'Orchid Road No. 99', '9 to 12 Orchid Road', '99 to 12 Orchid Road',
    '蘭花路第99號',
])
def test_explicit_number_markers_and_word_ranges_reject_contradictions(tmp_path, street):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    with HKRegionalMatcher(make_pack(tmp_path)) as matcher:
        assert matcher.match('Lantern Building\n' + street) is None


@pytest.mark.parametrize('text', [
    'Attn: Lantern Building\n12 Orchid Road', 'To: Lantern Building\n12 Orchid Road',
    'Example Person\n12 Orchid Road\nAttn: Lantern Building',
    'Example Person\nLantern Building Co.\n12 Orchid Road',
    'Example Person\nLantern Building GmbH\n12 Orchid Road',
    '12 Orchid Road Lantern Building Ltd',
])
def test_regional_aliases_cannot_use_company_or_recipient_occurrences(tmp_path, text):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    from world_address_engine.matching.country import CountryClassifier
    regional = make_pack(tmp_path)
    with HKRegionalMatcher(regional) as matcher:
        assert matcher.match(text) is None
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=regional) as classifier:
        assert classifier.classify(record(text)).country_code is None


@pytest.mark.parametrize('kind', ['building', 'district'])
@pytest.mark.parametrize('text', ['Orchid Road 蘭花路', 'Orchid Road\n蘭花路',
                                  'Example Person\nOrchid Road\n蘭花路',
                                  '12 Orchid Road\n蘭花路'])
def test_translated_component_groups_are_not_independent_roles(tmp_path, kind, text):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    path = make_pack(tmp_path)
    with closing(sqlite3.connect(path)) as db, db:
        db.execute('DELETE FROM hk_aliases WHERE kind=?', (kind,))
        db.execute('INSERT INTO hk_aliases SELECT address_id,?,language,name,search_key,derived,anchor '
                   "FROM hk_aliases WHERE kind='street'", (kind,))
    repin(path)
    with HKRegionalMatcher(path) as matcher:
        assert matcher.match(text) is None


@pytest.mark.parametrize('unit', ['Flat', 'Room', 'Floor', 'Unit', 'Suite'])
def test_unit_number_does_not_supply_street_house_number(tmp_path, unit):
    from world_address_engine.matching.hk_regional import HKRegionalMatcher
    from world_address_engine.matching.country import CountryClassifier
    text = f'Example Person\n{unit} 12, Orchid Road\nCopper District'
    regional = make_pack(tmp_path)
    with HKRegionalMatcher(regional) as matcher:
        assert matcher.match(text) is None
    with CountryClassifier(geo(tmp_path), catalogue(), hk_regional_db=regional) as classifier:
        assert classifier.classify(record(text)).country_code is None
