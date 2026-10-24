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
