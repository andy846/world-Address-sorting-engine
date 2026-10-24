"""Public geographic terms in invented fixtures, never private customer rows."""
import pytest

from tests.unit.test_country_inference import catalogue, record
from tests.unit.test_retrieve import geo, _row
from world_address_engine.matching.country import CountryClassifier


@pytest.mark.parametrize('tail', [
    'Tin Hau', 'Kwai Fong NT', 'Kwai Hing NT', 'Kwai Shing\nN T',
    'Tiu Keng Leng, NT', 'So Kwun Wat NT', 'Ma Wan NT',
    'Mei Foo Sun Chuen\nKL', 'On Lok Tsuen North, N.T.',
    'Clearwater Bay NT', 'Clear Water Bay\nNT', 'KLN Bay KL',
    '12 Nathan Road\nKL', '12 Argyle Street KL', '12 Nanking Street KL',
    '12 Granville Road KL', '12 Fa Yuen St\nHK KL',
    '12 Ice House Street\nCentral', '12 Wellington Street\nCentral',
    "12 Queen's Road Central", '12 Queen Victoria Street Central',
    '12 Wong Chuk Hang Road\nAberdeen',
    '12 Queenway\nAdmiralty', '12 Austin Road West\nTST East KL',
    '12 Des Voeux Road CentralHong Kong',
    '12 Tai Lin Pai Rd NT', '12 Kwai Cheong Rd NT', '12 Cheung Tat Road\nNT',
    '12 Kwai Fat Road NT', '12 Castle Peak Road\nKL',
    '12 Kwai Fung Crescent\nNT', '12 Example Road\nKwai Chng NT',
    '12 Example Road\nSymphony Bay\nNT',
    'Lippo Centre\n12 Queensway',
    'The Arch\n12 Austin Road West',
])
def test_additional_hk_locality_context(tmp_path, tail):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Example Person\nFlat 4, Example Building\n' + tail))
    assert found.country_code == 'HK'


@pytest.mark.parametrize('address,code', [
    ('中國青島市\n香港中路12號示例大廈', 'CN'),
    ('中国无锡市\n新加坡工业园\n示例路十二号', 'CN'),
    ('中国北京市\n示例泰国际大厦十二楼', 'CN'),
    ('中国深圳市\n示例德国际中心十二楼', 'CN'),
    ('12 Example Street\nNew South Wales\nAustralia 2000', 'AU'),
    ('中國澳門氹仔\n示例大廈十二樓', 'MO'),
    ('中国香港九龙\n示例街十二号', 'HK'),
    ('Example Tower China\nHong Kong City\n12 Example Road\nHK', 'HK'),
    ('Shenzhen-Hong Kong\nExample Workshop\n12 Example Road\nShenzhen, China', 'CN'),
    ('西安市\n示例路十二号', 'CN'),
    ('西安\n示例路十二号', 'CN'),
    ('中山市东区\n示例路十二号', 'CN'),
    ('合肥市蜀山区\n示例路十二号', 'CN'),
    ('惠东县吉隆镇\n示例路十二号', 'CN'),
    ('阳江市阳东区\n示例路十二号', 'CN'),
    ('广洲市天河区\n示例路十二号', 'CN'),
    ('南山区\n示例路十二号', 'CN'),
    ('12 Example Road\nLondon W1A 1AA', 'GB'),
    ('12 Example Road\nSeoul Korea', 'KR'),
])
def test_named_geographies_and_country_occurrence_roles(tmp_path, address, code):
    with CountryClassifier(geo(tmp_path)) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == code


@pytest.mark.parametrize('address,code', [
    ('12 Example Road\nWales', 'GB'),
    ('12 Example Road\nNew South Wales\nUnited Kingdom\nAustralia', None),
    ('中國\n澳門\n示例路十二號', None),
    ('中国深圳市\n香港\n示例路十二号', None),
    ('12 Singapore Road', None),
    ('12 Hong Kong Road', None),
    ('12 Example Road\nKL', None),
    ('12 Example Road\nNT', None),
    ('12 Nathan Road\nJapan', 'JP'),
    ('12 Example Road\nTin Hau\nUnited States', 'US'),
    ('12 Example Road\nLondon W1A 1AA\nFrance', 'FR'),
    ('12 Example Road\nSeoul Korea\nNorth Korea', 'KP'),
    ('12 Kwai Fat Road\nJapan', 'JP'),
    ('12 Example Road\nLippo Centre', None),
    ('12 Queensway', None),
    ('The Arch\n12 Example Road', None),
    ('12 Austin Road West', None),
    ('12 Example Road\nSingapore City', 'SG'),
    ('中国香港路十二号\n示例中心', 'CN'),
    ('中国香港大厦十二楼', 'CN'),
    ('中國澳門中心十二樓', 'CN'),
    ('12 Example Road\nChina\nHong Kong City\nHK', None),
    ('12 Example Road\nTin Hau\nTokyo', None),
    ('12 Example Road\nMa Wan NT\nTokyo', None),
    ('12 Example Road\nTokyo\nSeoul Korea', None),
    ('12 Example Road\nTokyo\nLondon W1A 1AA', None),
    ('Example Trading Ltd\nRETURNED MAIL UNKNOWN ADDRESS\n12 Example Road\nJapan', 'JP'),
])
def test_recall_changes_preserve_foreign_overrides_and_real_conflicts(tmp_path, address, code):
    with CountryClassifier(geo(tmp_path)) as classifier:
        found = classifier.classify(record('Example Person\n' + address))
    assert found.country_code == code


def test_returned_mail_marker_is_explained_without_guessing_company_country(tmp_path):
    with CountryClassifier(geo(tmp_path)) as classifier:
        found = classifier.classify(record('Example Trading Ltd\nRETURNED MAIL UNKNOWN ADDRESS\nY'))
    assert found.country_code is None
    assert found.reason == 'RETURNED_MAIL_NO_ADDRESS'


@pytest.mark.parametrize('tail', ['San Po Kong\nKL', 'TST\nKL', 'Kwai Fat Road NT'])
def test_short_alias_for_foreign_capital_does_not_erase_hk_context(tmp_path, tail):
    pack = geo(tmp_path, extra_rows=[_row(901, 'Kuala Lumpur', 'MY', 'P', 'PPLC', pop=1500000)],
               extra_aliases=['900\t901\ten\tKL\n'])
    with CountryClassifier(pack) as classifier:
        found = classifier.classify(record('Example Person\nFlat 4\n12 Example Road\n' + tail))
    assert found.country_code == 'HK'


def test_full_foreign_capital_still_conflicts_with_hk_context(tmp_path):
    pack = geo(tmp_path, extra_rows=[_row(901, 'Kuala Lumpur', 'MY', 'P', 'PPLC', pop=1500000)])
    with CountryClassifier(pack) as classifier:
        found = classifier.classify(record('Example Person\n12 Example Road\nSan Po Kong\nKuala Lumpur'))
    assert found.country_code is None
