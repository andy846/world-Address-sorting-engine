"""Synthetic context regressions; never copy customer address rows here."""

import pytest

from tests.unit.test_country_inference import catalogue, record
from tests.unit.test_retrieve import geo, _row
from world_address_engine.matching.country import CountryClassifier
from world_address_engine.matching.normalize import normalize_address
from world_address_engine.matching.retrieve import retrieve_candidates


@pytest.mark.parametrize('address', [
    '12 Example Road\nTST',
    '12 Example Road\nT.S.T.',
    '12 Example Road\nTsimshatsui',
    '12 Tak Hing Street\nJordan',
    '12 Nanking Street\nJordan KL',
    '12 Woosung Street\nJordan, KL',
    '12 Canton Road\nJordan KL',
    '12 Example Road\nCentral HK 1234',
    '12 Example Road, Jordan\nKLN, Hong Kong',
    '12 Des Voeux Road Central\nCentral',
    '12 Wing Kut Street\nCentral',
    '12 Connaught Place\nCentral',
    '12 Queensway\nAdmiralty',
    'The Example Building\n12 Austin Road West\nTST',
    '12 Example Road\nShek Mun, N.T.',
    '12 Example Road\nLai King NT',
])
def test_contextual_hong_kong_locations(tmp_path, address):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == 'HK'


@pytest.mark.parametrize('address', [
    '12 Example Road\nCentral', '12 Example Road\nAdmiralty',
    '12 Example Road\nKL', '12 Example Road\nNT', 'TST',
    'TST Trading Ltd\n12 Example Road',
    '12 Example Road\nAustin', '12 Example Road\nMary Hospital',
])
def test_generic_words_and_unanchored_abbreviations_do_not_assume_hk(tmp_path, address):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record(address))
    assert found.country_code != 'HK'


@pytest.mark.parametrize('address,code', [
    ('12 Example Road\nAmman\nJordan', 'JO'),
    ('12 Example Road\nJordan', 'JO'),
    ('12 Queen Street\nAdmiralty\nUnited States', 'US'),
    ('12 Example Road\nTST\nJapan', 'JP'),
    ('12 Tak Hing Street\nJordan\nJapan', 'JP'),
    ('12 Example Road\nHong Kong\nJapan', None),
    ('12 Example Road\nGuangdong Province\nKowloon', None),
])
def test_foreign_destinations_and_genuine_conflicts_are_preserved(tmp_path, address, code):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == code


@pytest.mark.parametrize('address', [
    '\u676d\u5dde\u5e02\u4f8b\u5b50\u8def\u5341\u53f7\n\u7f8e\u56fd\u4e2d\u5fc3',
    '\u6d59\u6c5f\u7701\u4f8b\u5b50\u8def\u5341\u53f7\n\u82f1\u570b\u5927\u5ec8',
    '\u5e7f\u4e1c\u7701\u6df1\u5733\u5e02\u76d0\u7530\u533a\n\u6c99\u5934\u89d2\u4f8b\u5b50\u8def\u5341\u53f7',
    '\u6df1\u5733\u5e02\u7f57\u6e56\u533a\n\u4f8b\u5b50\u8def\u5341\u53f7',
    '\u5167\u8499\u53e4\u81ea\u6cbb\u5340\n\u4f8b\u5b50\u8def\u5341\u53f7',
])
def test_mainland_admin_and_buildings_do_not_create_foreign_conflicts(tmp_path, address):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == 'CN'


@pytest.mark.parametrize('address', [
    '12 Jordan Road', '12 France Street', '12 United States Center',
    '\u7f8e\u56fd\u4e2d\u5fc3\u5341\u6a13', '\u65e5\u672c\u6a4b\u8def\u5341\u53f7',
])
def test_building_or_street_country_is_not_reintroduced_by_retrieval(tmp_path, address):
    pack = geo(tmp_path, extra_rows=[_row(901, 'Jordan', 'JO', 'A', 'PCLI', '00', 10000000)])
    with CountryClassifier(pack, catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code is None


def test_street_named_for_a_large_city_does_not_compete_with_destination(tmp_path):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n12 London Road\nTokyo'))
    assert found.country_code == 'JP'


def test_street_role_does_not_cross_address_line_boundaries(tmp_path):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\nLondon\nRoad 12'))
    assert found.country_code == 'GB'


def test_tiny_places_cannot_amplify_an_administrative_rival(tmp_path):
    extra = [_row(901, 'Alpha District', 'FR', 'A', 'ADM2')]
    extra += [_row(902 + i, name, 'FR', pop=250)
              for i, name in enumerate(('Birch', 'Cedar', 'Maple', 'Willow'))]
    with CountryClassifier(geo(tmp_path, extra_rows=extra), catalogue()) as classifier:
        found = classifier.classify(record(
            'Example Person\n12 Example Road\nTokyo\nAlpha District\nBirch Cedar Maple Willow'))
    assert found.country_code is None
    assert found.reason == 'MULTIPLE_PLAUSIBLE_COUNTRIES'


def test_display_evidence_truncation_does_not_erase_substantial_place(tmp_path):
    names = ['Hamlet' + chr(ord('a') + i) for i in range(20)]
    extra = [_row(901, 'Alpha District', 'FR', 'A', 'ADM2')]
    extra += [_row(902 + i, name, 'FR', pop=50000) for i, name in enumerate(names)]
    pack = geo(tmp_path, extra_rows=extra)
    text = 'Example Person\n12 Example Road\nAlpha District\n' + ' '.join(names)
    candidates = retrieve_candidates(pack, normalize_address(text))
    france = next(c for c in candidates if c.destination_id == 'FR')
    assert len(france.evidence) == 20
    assert len(france.place_support) == 21
    with CountryClassifier(pack, catalogue()) as classifier:
        found = classifier.classify(record(text))
    assert found.country_code == 'FR'


@pytest.mark.parametrize('address,code', [
    ('Example Person\n\u5167\u8499\u53e4\u81ea\u6cbb\u5340\n\u4f8b\u5b50\u8def\u5341\u53f7', 'CN'),
    ('Example Person\n12 Example Road\nInner Mongolia', 'CN'),
    ('Example Person\n12 Example Road\nMongolia', 'MN'),
])
def test_mongolia_country_and_mainland_region_use_full_catalogue(tmp_path, address, code):
    with CountryClassifier(geo(tmp_path)) as classifier:
        found = classifier.classify(record(address))
    assert found.country_code == code


@pytest.mark.parametrize('address,code', [
    ('12 Hong Kong House\nJordan', 'JO'),
    ('12 Nathan Road\nAmman\nJordan', 'JO'),
    ('12 Example Road\nHong Kong\nAmman\nJordan', None),
    ('12 Shenzhen Tower\nTokyo', 'JP'),
    ('12 Shek Mun Building\nTokyo', 'JP'),
    ('12 Queensway\nAdmiralty House\nTokyo', 'JP'),
])
def test_final_review_foreign_destinations_survive_misleading_hk_context(tmp_path, address, code):
    pack = geo(tmp_path, extra_rows=[
        _row(901, 'Jordan', 'JO', 'A', 'PCLI', '00', 10000000),
        _row(902, 'Amman', 'JO', 'P', 'PPLC', '01', 4000000),
    ])
    with CountryClassifier(pack, catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == code
