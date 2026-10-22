"""Regressions for the independent review of commits 525e0e2 / 63d2c32.

Every case here previously produced a confidently WRONG destination code or
a false conflict. They are grouped by the review finding they close.
"""

from pathlib import Path

import pytest

from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.matching.classify import classify_record
from world_address_engine.models import AddressRecord
from tests.hkp_master_fixture import build_master


def _row(i, name, country, fclass='P', fcode='PPL', admin1='01', pop='1000'):
    return '\t'.join([str(i), name, name, '', '0', '0', fclass, fcode, country, '',
                       admin1, '', '', '', str(pop), '', '', 'UTC', '2024-01-01'])


COUNTRIES = [
    ('guyana', 'GY', 'GY', 'Guyana', '蓋亞那', '圭亚那'),
    ('united-states', 'US', 'US', 'United States', '美國', '美国'),
    ('japan', 'JP', 'JP', 'Japan', '日本', '日本'),
    ('china', 'CN', 'CN', 'China', '中國', '中国'),
    ('hong-kong', 'HK', 'HK', 'Hong Kong', '香港', '香港'),
    ('india', 'IN', 'IN', 'India', '印度', '印度'),
    ('singapore', 'SG', 'SG', 'Singapore', '新加坡', '新加坡'),
    ('macau', 'MO', 'MO', 'Macau', '澳門', '澳门'),
]


@pytest.fixture(scope="module")
def master(tmp_path_factory):
    return build_master(tmp_path_factory.mktemp("review-master"), countries=COUNTRIES)


@pytest.fixture(scope="module")
def geo(tmp_path_factory):
    """A gazetteer with the places the review reproductions depend on."""
    directory = tmp_path_factory.mktemp("review-geo")
    source = directory / 'source'
    source.mkdir()
    rows = [
        _row(1, 'Guyana', 'GY', 'A', 'PCLI', '00', 800000),
        _row(2, 'New Amsterdam', 'US', 'P', 'PPL', '01', 1200),
        _row(3, 'Georgia', 'GE', 'A', 'PCLI', '00', 4200000),
        _row(4, 'Georgia', 'US', 'A', 'ADM1', 'GA', 10711908),
        _row(5, 'Savannah', 'US', 'P', 'PPL', 'GA', 147780),
        _row(6, 'Poland', 'PL', 'A', 'PCLI', '00', 37978548),
        _row(7, 'New York', 'US', 'A', 'ADM1', 'NY', 19677151),
        _row(8, 'Turks and Caicos Islands', 'TC', 'A', 'PCLI', '00', 45000),
        _row(9, 'Japan', 'JP', 'A', 'PCLI', '00', 123366734),
        _row(10, 'United States', 'US', 'A', 'PCLI', '00', 341784857),
        _row(11, 'China', 'CN', 'A', 'PCLI', '00', 1406585000),
        _row(12, 'Hong Kong', 'HK', 'A', 'PCLI', '00', 7500700),
        _row(13, 'India', 'IN', 'A', 'PCLI', '00', 1463865525),
        _row(14, 'Singapore', 'SG', 'A', 'PCLI', '00', 6111175),
        _row(15, 'Macau', 'MO', 'A', 'PCLS', '00', 685900),
        _row(16, 'Denver', 'US', 'P', 'PPL', 'CO', 727211),
        _row(17, 'Marks', 'US', 'P', 'PPL', 'NY', 1200),
        _row(18, 'Spencer', 'US', 'P', 'PPL', 'NY', 1200),
        _row(19, 'United States Minor Outlying Islands', 'UM', 'A', 'PCLI', '00', 300),
        _row(20, 'Wake', 'UM', 'P', 'PPL', '01', 1000),
        _row(21, 'Wake', 'US', 'P', 'PPL', 'NC', 100000),
    ]
    (source / 'allCountries.txt').write_text('\n'.join(rows) + '\n', encoding='utf8')
    (source / 'alternateNamesV2.txt').write_text(
        '1\t2\ten\tCo-operative Republic of Guyana\n', encoding='utf8')
    path = directory / 'geo.db'
    build_geonames_pack(source, path, 'EXTENDED_GLOBAL')
    return path


def classify(text, geo_db, master, hint=None):
    record = AddressRecord(1, 'sample.csv', None, '0001', {'Address': text}, text, hint)
    return classify_record(record, geo_db, master.db_path, master.approval)


# --- review P0-3 / P1-2: the marker list misfires on short and hyphenated tokens

def test_official_country_name_is_not_suppressed_by_the_word_co(geo, master):
    result = classify('Co-operative Republic of Guyana', geo, master)
    assert result.status == 'MATCHED' and result.hkp_code == 'GY'


def test_hyphenated_country_name_does_not_lose_to_an_unrelated_place(geo, master):
    result = classify('New Amsterdam, Co-operative Republic of Guyana', geo, master)
    assert result.hkp_code != 'US'
    assert result.status == 'MATCHED' and result.hkp_code == 'GY'


def test_two_letter_state_code_is_not_a_company_marker(geo, master):
    """'CO' is Colorado, not 'Co.' as a company suffix."""
    result = classify('Denver, CO 80202 United States', geo, master)
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


# --- review P0-2: company suppression must not delete a real contradiction

def test_company_suppression_does_not_hide_a_contradiction_with_the_hint(geo, master):
    result = classify('ACME JAPAN LTD', geo, master, hint='US')
    assert result.status == 'REVIEW_CONFLICT'
    assert result.hkp_code is None


def test_hint_that_agrees_with_the_withdrawn_name_is_still_matched(geo, master):
    result = classify('ACME JAPAN LTD', geo, master, hint='JP')
    assert result.status == 'MATCHED' and result.hkp_code == 'JP'


# --- review P1-1: a gazetteer country entity is geography, not an assertion

def test_country_entity_does_not_conflict_with_an_explicit_country_name(geo, master):
    """'Georgia' here is the US state, and Georgia the country is not named."""
    result = classify('Savannah, Georgia 30301, United States', geo, master)
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


def test_territory_inside_its_parent_country_is_matched(geo, master):
    result = classify('Turks and Caicos Islands, United States', geo, master)
    assert result.status == 'MATCHED' and result.hkp_code == 'US'


# --- review P1-3: company names without a listed legal marker

@pytest.mark.parametrize("text,code", [
    ('China Telecom', 'CN'),
    ('Hong Kong Airlines', 'HK'),
    ('India Import', 'IN'),
    ('CHINA CONSTRUCTION', 'CN'),
])
def test_country_word_inside_a_company_name_is_not_evidence(text, code, geo, master):
    result = classify(text, geo, master)
    assert result.hkp_code != code


# --- review P1-4: the MATCHED bar must sit above a single insignificant place

def test_two_insignificant_place_tokens_do_not_assert_a_country(geo, master):
    result = classify('Marks & Spencer', geo, master)
    assert result.status != 'MATCHED'
    assert result.hkp_code is None


# --- review P0-1: a country name that is only the start of a longer name

def test_country_name_inside_a_longer_country_name_is_not_asserted(geo, master):
    """'Wake, United States Minor Outlying Islands' is not the United States."""
    result = classify('Wake, United States Minor Outlying Islands', geo, master)
    assert result.status == 'REVIEW_CODE_MAPPING', result.reason
    assert result.hkp_code is None


def test_the_shorter_country_name_still_works_on_its_own(geo, master):
    result = classify('Wake, United States', geo, master)
    assert result.status == 'MATCHED' and result.hkp_code == 'US'
