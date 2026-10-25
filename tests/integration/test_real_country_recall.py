"""Public-term recall regressions against both installed real k2 databases."""
import os
from pathlib import Path

import pytest

from tests.unit.test_country_inference import record
from world_address_engine.matching.country import CountryClassifier


@pytest.fixture(params=['compact', 'extended'])
def classifier(request):
    root = Path(os.environ.get('WASE_INSTALLED_PACK_DIR', Path(__file__).resolve().parents[2] / 'packs'))
    generation = os.environ.get('WASE_PACK_GENERATION', '2026-10-22-k2')
    path = root / f'geonames-{request.param}-global-{generation}' / 'pack.db'
    if not path.is_file():
        pytest.skip('installed real reference database absent')
    with CountryClassifier(path) as value:
        yield value


@pytest.mark.parametrize('tail,code', [
    ('12 Example Street\nLondon W6 0NB', 'GB'),
    ('12 Example Street\nSeoul Korea', 'KR'),
    ('12 Example Street\nNew South Wales\nAustralia 2000', 'AU'),
    ('12 Example Street\nKowloon City KL', 'HK'),
    ('12 Example Street\nMa Wan NT', 'HK'),
    ('12 Example Street\nKwai Fong NT', 'HK'),
    ('中国山东省青岛市\n香港东路十二号', 'CN'),
    ('中国青岛市\n香港中路十二号', 'CN'),
    ('12 Example Street\nClear Water Bay NT', 'HK'),
    ('12 Example Street\nSymphony Bay NT', 'HK'),
    ('12 Example Street\nTin Hau\nJapan', 'JP'),
    ('12 Example Street\nLondon W6 0NB\nFrance', 'FR'),
])
def test_real_country_context_recall(classifier, tail, code):
    assert classifier.classify(record('Example Person\n' + tail)).country_code == code


@pytest.mark.parametrize('text', [
    'MAN ON BUILDING\n288 LAI CHI KOK ROAD',
    'TAI PO MERCHANTS ASSOCIATION LTD. & NEW TERRITORIES HEUNG YEE KUK BUILDING\n2A YAN HING STREET',
])
def test_real_compound_hk_street_does_not_infer_foreign_homonym(classifier, text):
    result = classifier.classify(record(text))
    assert result.country_code is None
    assert result.reason == 'NO_GEOGRAPHIC_MATCH'


@pytest.mark.parametrize('text', [
    'MAN ON BUILDING\n288 LAI CHI KOK ROAD',
    'TAI PO MERCHANTS ASSOCIATION LTD. & NEW TERRITORIES HEUNG YEE KUK BUILDING\n2A YAN HING STREET',
])
def test_real_compound_hk_street_resolves_with_official_pair(classifier, text):
    regional = Path(__file__).resolve().parents[2] / 'packs/hk-bilingual-als-2026-10-23-r1-partial/pack.db'
    if not regional.is_file():
        pytest.skip('installed real ALS regional database absent')
    with CountryClassifier(classifier.geo_db, hk_regional_db=regional) as enabled:
        result = enabled.classify(record(text))
    assert result.country_code == 'HK'
    assert result.status == 'INFERRED'
    assert result.reason == 'HK_REGIONAL_ADDRESS_MATCH'
