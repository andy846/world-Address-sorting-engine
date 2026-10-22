"""A country name followed by a postal code is still a country name.

"LONDON, UNITED KINGDOM EC1A 1BB" names a country and a postcode. The
trailing-word rule that keeps "China Telecom" from being geographic evidence
used to treat "D02" and "EC1A" as company words, so the country was dropped
and the address was left without a destination.
"""

import pytest

from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.matching.classify import classify_record
from world_address_engine.models import AddressRecord
from tests.hkp_master_fixture import build_master

COUNTRIES = [
    ('united-kingdom', 'GB', 'GB', 'United Kingdom', '英國', '英国'),
    ('ireland', 'IE', 'IE', 'Ireland', '愛爾蘭', '爱尔兰'),
    ('canada', 'CA', 'CA', 'Canada', '加拿大', '加拿大'),
    ('japan', 'JP', 'JP', 'Japan', '日本', '日本'),
    ('china', 'CN', 'CN', 'China', '中國', '中国'),
    ('united-states', 'US', 'US', 'United States', '美國', '美国'),
]


def _row(i, name, country, fclass='P', fcode='PPL', admin1='01', pop='1000'):
    return '\t'.join([str(i), name, name, '', '0', '0', fclass, fcode, country, '',
                       admin1, '', '', '', str(pop), '', '', 'UTC', '2024-01-01'])


@pytest.fixture(scope="module")
def master(tmp_path_factory):
    return build_master(tmp_path_factory.mktemp("postal-master"), countries=COUNTRIES)


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    directory = tmp_path_factory.mktemp("postal-geo")
    source = directory / 'source'
    source.mkdir()
    rows = [
        _row(1, 'London', 'GB', 'P', 'PPLC', 'GLA', 8961989),
        _row(2, 'Dublin', 'IE', 'P', 'PPLC', '07', 1173179),
        _row(3, 'Ottawa', 'CA', 'P', 'PPLC', '08', 1017244),
        _row(4, 'Tokyo', 'JP', 'P', 'PPLC', '40', 13960000),
        _row(5, 'China', 'CN', 'A', 'PCLI', '00', 1406585000),
        _row(6, 'United Kingdom', 'GB', 'A', 'PCLI', '00', 67736802),
        _row(7, 'Ireland', 'IE', 'A', 'PCLI', '00', 5023109),
        _row(8, 'Canada', 'CA', 'A', 'PCLI', '00', 38929902),
        _row(9, 'Japan', 'JP', 'A', 'PCLI', '00', 123366734),
        _row(10, 'United States', 'US', 'A', 'PCLI', '00', 341784857),
        _row(11, 'Telecom', 'CN', 'P', 'PPL', '01', 5000),
    ]
    (source / 'allCountries.txt').write_text('\n'.join(rows) + '\n', encoding='utf8')
    (source / 'alternateNamesV2.txt').write_text('', encoding='utf8')
    path = directory / 'geo.db'
    build_geonames_pack(source, path, 'EXTENDED_GLOBAL')
    return path


def classify(text, geo_db, master, hint=None):
    record = AddressRecord(1, 'sample.csv', None, '0001', {'Address': text}, text, hint)
    return classify_record(record, geo_db, master.db_path, master.approval)


@pytest.mark.parametrize("text,code", [
    ('London, United Kingdom EC1A 1BB', 'GB'),
    ('Dublin, Ireland D02', 'IE'),
    ('Ottawa, Canada K1A 0B1', 'CA'),
    ('London, United Kingdom EC1A 1BB, Floor 3', 'GB'),
])
def test_country_name_before_a_postal_code_is_still_evidence(text, code, geo, master):
    result = classify(text, geo, master)
    assert result.status == 'MATCHED', result.reason
    assert result.hkp_code == code


def test_a_company_word_after_the_country_is_still_withdrawn(geo, master):
    """The fix must not turn every trailing word into harmless noise."""
    result = classify('China Telecom', geo, master)
    assert result.hkp_code != 'CN'
