"""Country statistics accept explainable estimates without postal approval."""
from pathlib import Path
from types import SimpleNamespace

import pytest

from tests.unit.test_retrieve import geo, _row
from world_address_engine.models import AddressRecord
from world_address_engine.matching.country import CountryClassifier, CountryInference


def catalogue():
    names = {
        'HK': ('Hong Kong', '\u9999\u6e2f'), 'CN': ('China', '\u4e2d\u570b'),
        'JP': ('Japan', '\u65e5\u672c'), 'US': ('United States', '\u7f8e\u570b'),
        'GB': ('United Kingdom', '\u82f1\u570b'), 'CA': ('Canada', '\u52a0\u62ff\u5927'),
        'IN': ('India', '\u5370\u5ea6'), 'FR': ('France', '\u6cd5\u570b'),
        'MO': ('Macau', '\u6fb3\u9580'), 'TW': ('Taiwan', '\u53f0\u7063'),
        'TP': ('Timor-Leste', '\u6771\u5e1d\u6c76'),
        'XO': ('Kosovo', '\u79d1\u7d22\u6c83'), 'XK': ('Caroline Islands', '\u52a0\u7f85\u6797\u7fa4\u5cf6'),
        'JO': ('Jordan', '\u7d04\u65e6'),
    }
    return SimpleNamespace(entries={code: SimpleNamespace(
        code=code, name_en=en, name_tc=tc, aliases=()) for code, (en, tc) in names.items()},
        geo_to_code={**{k: k for k in names if k not in {'TP', 'XO', 'XK'}},
                     'TL': 'TP', 'XK': 'XO'})


def record(text, **kw):
    return AddressRecord(1, 'synthetic.csv', None, '0001', {'Address': text}, text,
                         kw.get('hint'), kw.get('input_error'))


@pytest.mark.parametrize('text,code', [
    ('Example Person\nFlat 2, Example Building\nHK', 'HK'),
    ('Example Person\n12 Example Road\nH.K.', 'HK'),
    ('Example Person\n12 Example Road\nKLN', 'HK'),
    ('Example Person\n12 Example Road\nTuen Mun, N.T.', 'HK'),
    ('Example Person\n12 Example Road\nSha Tin', 'HK'),
    ('Example Person\n12 Example Road\nKowloon', 'HK'),
    ('Example Person\n\u89c0\u5858\u958b\u6e90\u9053\u5341\u865f', 'HK'),
    ('Example Person\n\u5e7f\u4e1c\u7701\u6df1\u5733\u5e02\u793a\u4f8b\u8def\u5341\u53f7', 'CN'),
    ('Example Person\nGuangdong Province\nExample Street', 'CN'),
    ('Example Person\n12 Example Road\nUSA', 'US'),
    ('Example Person\n12 Example Road\nUK', 'GB'),
    ('France\n12 Rue Example', 'FR'),
    ('Example Person\nLondon Road, Mumbai, India', 'IN'),
    ('Example Person\n\u4e2d\u534e\u4eba\u6c11\u5171\u548c\u56fd\u9999\u6e2f\u7279\u522b\u884c\u653f\u533a', 'HK'),
    ('Example Person\n12 Example Road\nTimor-Leste', 'TP'),
    ('Example Person\n12 Example Road\nKosovo', 'XO'),
    ('Example Person\n12 Example Road\nCaroline Islands', 'XK'),
])
def test_country_and_region_evidence(tmp_path, text, code):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        result = classifier.classify(record(text))
    assert result.country_code == code
    assert result.status in {'DETERMINED', 'INFERRED'}


def test_one_substantial_city_can_be_estimated(tmp_path):
    pack = geo(tmp_path, extra_rows=[_row(901, 'Tokyo', 'US', pop=250)])
    with CountryClassifier(pack, catalogue()) as classifier:
        found = classifier.classify(record('Example Person\n12 Example Road\nTokyo'))
    assert found.country_code == 'JP'
    assert found.status == 'INFERRED'


@pytest.mark.parametrize('text', [
    'Example Person\n12 Example Road\nSpringfield',
    'CHINA CONSTRUCTION LTD', 'Example Person\nChina Mobile',
    'Example Person\n12345', 'Example Person\nExample Street',
    'Example Person\nN.T.', 'Example Person\nChina\nJapan',
])
def test_ambiguous_or_non_geographic_text_is_not_filled_from_batch(tmp_path, text):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record(text))
    assert found.status == 'UNRESOLVED'
    assert found.country_code is None


def test_input_error_is_not_classified(tmp_path):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        found = classifier.classify(record('Hong Kong', input_error='UNDECODABLE_TEXT'))
    assert found.country_code is None and found.reason == 'UNDECODABLE_TEXT'


def test_result_invariants():
    with pytest.raises(ValueError):
        CountryInference(1, 'HK', 'UNRESOLVED', 'conflict')
    with pytest.raises(ValueError):
        CountryInference(1, None, 'DETERMINED', 'country')


def test_country_analysis_does_not_modify_the_source_record(tmp_path):
    r = record('Example Person\n12 Example Road\nKLN')
    before = dict(r.fields)
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        classifier.classify(r)
    assert dict(r.fields) == before


@pytest.mark.parametrize('text,code', [
    ('Mr Jordan\n12 Example Road\nTokyo', 'JP'),
    ('Mr Jordan\n12 Example Road\nJapan', 'JP'),
    ('Example Person\n12 Example Road\nHong Kong, China', 'HK'),
    ('Example Person\n12 Example Road\nMacau, China', 'MO'),
    ('Example Person\n12 Shanghai Street\nMong Kok', 'HK'),
    ('Example Person\nShanghai Trading 2\n12 Example Road\nTokyo', 'JP'),
    ('Example Person\n12 Example Road\nSheung Wan', 'HK'),
    ('Example Person\n12 Example Road\nTSUENWAN', 'HK'),
    ('Example Person\n12 Example Road\nExample District H.K.', 'HK'),
    ('Example Person\n12 Example Road\nExample District KLN', 'HK'),
    ('Example Person\n12 Example Road, Hong Kong, China', 'HK'),
    ('Example Person\nHong  Kong, China', 'HK'),
    ('Example Trading Ltd\nAlice Jordan\n12 Example Road\nTokyo', 'JP'),
    ('Example Person\n12 Hunan Rd\nTokyo', 'JP'),
    ('Example Person\n12 Shanghai St.\nMong Kok', 'HK'),
    ('Example Person\n12 Bank Street London', 'GB'),
    ('Example Person\nP.R.CHINA\n12 Example Road', 'CN'),
    ('Example Person\n\u4e2d\u56fd\u5e7f\u4e1c\u7701\n12 Example Road', 'CN'),
    ('Tokyo Japan', 'JP'),
])
def test_independent_review_and_locality_regressions(tmp_path, text, code):
    with CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        result = classifier.classify(record(text))
    assert result.country_code == code
