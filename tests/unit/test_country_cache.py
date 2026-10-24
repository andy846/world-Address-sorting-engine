"""Bounded cache behavior for repeated batches, using invented addresses."""
from tests.unit.test_country_inference import catalogue, record
from tests.unit.test_retrieve import geo
from world_address_engine.matching import country


def test_ten_thousand_address_batch_reuses_inferences_on_second_cycle(tmp_path, monkeypatch):
    calls = []
    with country.CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        original = classifier._infer
        def counted(text, hint):
            calls.append(1)
            return original(text, hint)
        monkeypatch.setattr(classifier, '_infer', counted)
        first = [classifier.classify(record(f'Example Person\nFlat {i}, Example Building\nHong Kong'))
                 for i in range(10000)]
        assert len(calls) == 10000
        second = [classifier.classify(record(f'Example Person\nFlat {i}, Example Building\nHong Kong'))
                  for i in range(10000)]
        assert len(calls) == 10000, 'a repeated 10,000-row working set should remain cached'
        assert first == second


def test_entry_limit_evicts_lru_and_recency_hits_preserve_results(tmp_path, monkeypatch):
    monkeypatch.setattr(country, 'CACHE_MAX_ENTRIES', 2, raising=False)
    with country.CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        first = record('Flat 1\nHong Kong')
        second = record('Flat 2\nJapan')
        third = record('Flat 3\nChina')
        assert classifier.classify(first).country_code == 'HK'
        assert classifier.classify(second).country_code == 'JP'
        classifier.classify(first)
        classifier.classify(third)
        assert len(classifier._cache) == 2
        assert (first.address_text, None) in classifier._cache
        assert (second.address_text, None) not in classifier._cache
        assert classifier.classify(second).country_code == 'JP'


def test_text_budget_bounds_large_unicode_and_hint_keys_and_resets_on_close(tmp_path, monkeypatch):
    monkeypatch.setattr(country, 'CACHE_MAX_TEXT_BYTES', 110, raising=False)
    with country.CountryClassifier(geo(tmp_path), catalogue()) as classifier:
        records = [record('例' * 10 + str(i), hint='Japan') for i in range(20)]
        for item in records:
            assert classifier.classify(item).country_code == 'JP'
            assert sum(len((key[0] + (key[1] or '')).encode('utf-8'))
                       for key in classifier._cache) <= 110
        oversized = record('例' * 100, hint='Japan')
        assert classifier.classify(oversized).country_code == 'JP'
        assert (oversized.address_text, oversized.country_hint) not in classifier._cache
    assert not classifier._cache
