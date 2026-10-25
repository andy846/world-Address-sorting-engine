"""Synthetic compound-street evidence guards; no customer inputs."""
import pytest

from tests.unit.test_country_inference import record
from tests.unit.test_retrieve import geo, _row
from world_address_engine.matching.country import CountryClassifier


@pytest.fixture
def pack(tmp_path):
    return geo(tmp_path, extra_rows=[
        _row(950, 'Lai', 'TD', 'P', 'PPLA', pop=100000),
        _row(951, 'Yan', 'MY', 'A', 'ADM2'),
        _row(952, 'Birch', 'FR', 'P', 'PPLC', pop=500000),
        _row(953, 'Washington D C', 'US', 'P', 'PPLC', pop=500000),
        _row(954, 'Cedar Basin', 'FR', 'P', 'PPLC', pop=500000),
    ], extra_aliases=['999\t953\ten\tWashington\n'])


@pytest.mark.parametrize('street', [
    '288 Lai Chi Kok Road', '2A Yan Hing Street',
    '12 Birch Orchard Avenue', '12-14 Birch Orchard Rd.',
    'Flat 2, 288 Lai Chi Kok Road', '12 Birch Orchard Lane',
    '99999999 Lai Chi Kok Road',
])
def test_numbered_compound_street_cannot_supply_a_city_country(pack, street):
    with CountryClassifier(pack) as classifier:
        found = classifier.classify(record('Example Person\n' + street))
    assert found.country_code is None
    assert found.reason == 'NO_GEOGRAPHIC_MATCH'


@pytest.mark.parametrize('street', ['288 Lai Chi Kok Road', '2A Yan Hing Street'])
@pytest.mark.parametrize('destination', ['\nTokyo', ', Tokyo', ' Tokyo'])
def test_independent_city_survives_a_compound_street(pack, street, destination):
    with CountryClassifier(pack) as classifier:
        found = classifier.classify(record('Example Person\n' + street + destination))
    assert found.country_code == 'JP'


@pytest.mark.parametrize('text,code', [
    ('288 Lai Chi Kok Road\nLai', 'TD'),
    ('2A Yan Hing Street\nYan', 'MY'),
    ('12 Example Road\nLai', 'TD'),
    ('12 Example Road\nYan', 'MY'),
    ('12 Birch Orchard Avenue\nJapan', 'JP'),
    ('288 Lai Chi Kok Road\nMalaysia', 'MY'),
    ('2A Yan Hing Street\nChad', 'TD'),
    ('288 Lai Chi Kok Road\nJapan\nFrance', None),
    ('Lai, 12 Birch Orchard Road', 'TD'),
    ('288 Lai Chi Kok Road, Lai', 'TD'),
    ('2A Yan Hing Street, Yan', 'MY'),
    ('12 Birch Orchard Road, London', 'GB'),
    ('12 Birch Orchard Road\nBirch', 'FR'),
])
def test_independent_homonyms_and_explicit_countries_remain(pack, text, code):
    with CountryClassifier(pack) as classifier:
        assert classifier.classify(record('Example Person\n' + text)).country_code == code


@pytest.mark.parametrize('city,code', [('Washington, D.C.', 'US'), ('New, Delhi', 'IN')])
def test_multiword_city_alias_across_punctuation_remains(pack, city, code):
    with CountryClassifier(pack) as classifier:
        result = classifier.classify(record('Example Person\n12 Example Road\n' + city))
    assert result.country_code == code


def test_removing_street_cannot_join_unrelated_words_into_a_city(pack):
    with CountryClassifier(pack) as classifier:
        result = classifier.classify(record(
            'Example Person\n12 Cedar Basin Road\nCedar, 24 Example Road Basin'))
    assert result.country_code is None
