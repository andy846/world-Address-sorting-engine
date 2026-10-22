import contextlib
import time

from pathlib import Path
from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.matching import retrieve as retrieve_module
from world_address_engine.matching.retrieve import retrieve_candidates
from world_address_engine.matching.normalize import normalize_address


def _row(i, name, country, fclass='P', fcode='PPL', admin1='01', pop='1000'):
    return '\t'.join([str(i), name, name, '', '0', '0', fclass, fcode, country, '', admin1,
                       '', '', '', str(pop), '', '', 'UTC', '2024-01-01'])


def geo(tmp_path, extra_rows=(), extra_aliases=()):
    source = tmp_path / 'source'
    source.mkdir(exist_ok=True)
    rows = [
        _row(1, 'Tokyo', 'JP', pop=13960000),
        _row(2, 'Shinjuku', 'JP', 'P', 'PPLX', '40', 349385),
        _row(3, 'London', 'GB', pop=8961989),
        _row(4, 'Mumbai', 'IN', pop=12691836),
        _row(5, 'Springfield', 'US', pop=170188),
        _row(6, 'Springfield', 'CA', pop=100000),
        _row(7, 'India', 'IN', 'A', 'PCLI', '00', 1463865525),
        _row(8, 'Japan', 'JP', 'A', 'PCLI', '00', 123366734),
        _row(9, 'Street', 'GB', pop=12911),
        _row(10, 'Main', 'GB', pop=2000),
        _row(11, 'New Delhi', 'IN', pop=329410),
        _row(12, 'Macau', 'MO', 'P', 'PPLC', '02', 649335),
        _row(13, 'Macau Special Administrative Region', 'MO', 'A', 'PCLS', '00', 685900),
        _row(14, 'Timor-Leste', 'TL', 'A', 'PCLI', '00', 1418517),
        _row(15, 'Singapore', 'SG', 'A', 'PCLI', '00', 6111175),
        _row(16, 'China', 'CN', 'A', 'PCLI', '00', 1406585000),
        _row(17, 'Illinois', 'US', 'A', 'ADM1', 'IL', 12710158),
        _row(18, 'France', 'FR', 'A', 'PCLI', '00', 68720337),
        _row(19, 'Ontario', 'CA', 'A', 'ADM1', '08', 14100000),
        _row(20, 'United States', 'US', 'A', 'PCLI', '00', 341784857),
    ] + list(extra_rows)
    (source / 'allCountries.txt').write_text('\n'.join(rows) + '\n', encoding='utf8')
    (source / 'alternateNamesV2.txt').write_text(
        '1\t11\ten\tDelhi\n2\t13\ten\tMacau\n3\t16\tzh\t中国\n'
        + ''.join(extra_aliases), encoding='utf8')
    path = tmp_path / 'geo.db'
    build_geonames_pack(source, path, 'EXTENDED_GLOBAL')
    return path


def _by_code(found):
    return {c.destination_id: c for c in found}


def test_shinjuku_tokyo_proposes_jp(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('Shinjuku, Tokyo'), None)
    assert found[0].destination_id == 'JP'
    assert len(found[0].evidence) == 2


def test_mumbai_india_does_not_propose_gb_from_london_road(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('London Road, Mumbai, India'), None)
    by_code = _by_code(found)
    assert 'IN' in by_code and len(by_code['IN'].evidence) >= 2
    if 'GB' in by_code:
        assert by_code['IN'].score > by_code['GB'].score


def test_springfield_without_other_context_is_ambiguous(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('Main Street, Springfield'), None)
    assert {c.destination_id for c in found} == {'US', 'CA'}


def test_only_twenty_candidates_returned(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('Tokyo Mumbai London Springfield Shinjuku'), None, limit=2)
    assert len(found) <= 2


def test_admin_hierarchy_prevents_false_link(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('Tokyo Mumbai'), None)
    assert len(found) >= 2
    assert all(c.destination_id in ('JP', 'IN') for c in found)


def test_country_entity_is_reported_as_such(tmp_path):
    india = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('India'), None))['IN']
    assert india.country_entity is True
    assert india.support >= 0.6


def test_repeated_place_rows_do_not_saturate_support(tmp_path):
    """Many rows for one term must not inflate the evidence mass."""
    found = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('Springfield'), None))
    assert found['US'].support < 0.3
    assert found['US'].token_count == 1


def test_generic_address_words_are_not_geographic_evidence(tmp_path):
    """'Main' and 'Street' are places in the fixture but never address evidence."""
    found = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('Main Street, Springfield'), None))
    assert 'GB' not in found
    assert found['US'].token_count == 1


def test_population_scales_the_populated_weight(tmp_path):
    found = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('Springfield'), None))
    assert found['US'].support > found['CA'].support


def test_a_place_matching_several_terms_counts_once(tmp_path):
    """'New Delhi' also matches the alias 'Delhi'; it must contribute one weight."""
    india = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('New Delhi'), None))['IN']
    assert india.token_count == 1
    # A single term can never weigh more than one populated-place weight.
    assert india.support < 0.26


def test_hyphenated_place_names_are_found(tmp_path):
    tl = _by_code(retrieve_candidates(geo(tmp_path), normalize_address('Timor-Leste'), None))['TL']
    assert tl.country_entity is True
    assert tl.support >= 0.6


def test_structured_hint_is_reported_even_without_geography(tmp_path):
    found = retrieve_candidates(geo(tmp_path), normalize_address('Nowhere'), 'JP')
    assert 'JP' in {c.destination_id for c in found}
    assert 'STRUCTURED_COUNTRY_HINT' in _by_code(found)['JP'].evidence


def test_limit_zero_returns_nothing(tmp_path):
    assert retrieve_candidates(geo(tmp_path), normalize_address('Tokyo'), None, limit=0) == []


def _statement_counter(monkeypatch):
    """Count the SELECT statements a retrieval issues."""
    counter = {'n': 0}
    original = retrieve_module.open_db

    @contextlib.contextmanager
    def counting(path):
        with original(path) as conn:
            def trace(statement):
                if statement.lstrip().upper().startswith('SELECT'):
                    counter['n'] += 1
            conn.set_trace_callback(trace)
            yield conn

    monkeypatch.setattr(retrieve_module, 'open_db', counting)
    return counter


def test_long_country_name_is_reachable(tmp_path):
    """A country name longer than four tokens must still resolve to itself."""
    db = geo(tmp_path, extra_rows=[
        _row(21, 'United States Minor Outlying Islands', 'UM', 'A', 'PCLI', '00', '300')])
    found = _by_code(retrieve_candidates(
        db, normalize_address('Wake, United States Minor Outlying Islands'), None))
    assert 'UM' in found
    assert found['UM'].country_entity is True
    assert found['UM'].support >= 0.6


def test_punctuated_place_names_are_reachable(tmp_path):
    """'St John's' must reach the place that is stored as "St. John's"."""
    db = geo(tmp_path, extra_rows=[_row(22, "St. John's", 'CA', 'P', 'PPL', '01', '100000')])
    found = _by_code(retrieve_candidates(
        db, normalize_address("St John's, Newfoundland"), None))
    assert 'CA' in found
    assert found['CA'].support > 0.1


def test_chinese_evidence_survives_a_long_address(tmp_path):
    """A long address must not truncate away every Chinese name."""
    db = geo(tmp_path,
             extra_rows=[_row(23, 'Hong Kong', 'HK', 'A', 'PCLS', '00', '7500000')],
             extra_aliases=['4\t23\tzh\t香港\n'])
    long_prefix = ' '.join('word%03d' % index for index in range(120))
    found = _by_code(retrieve_candidates(
        db, normalize_address(long_prefix + ' 香港'), None))
    assert 'HK' in found
    assert found['HK'].country_entity is True


def test_a_very_common_term_keeps_every_country_it_mentions(tmp_path):
    """A term matching hundreds of rows must not lose whole countries."""
    rows = [_row(100 + i, 'Buena Vista', 'US', 'P', 'PPL', '01', str(500000 - i))
            for i in range(450)]
    rows += [_row(600 + i, 'Buena Vista', code, 'P', 'PPL', '01', '10')
             for i, code in enumerate(('AW', 'BR', 'CL', 'CO', 'EC', 'ES'))]
    db = geo(tmp_path, extra_rows=rows)
    found = _by_code(retrieve_candidates(db, normalize_address('Buena Vista, Brazil'), None))
    assert {'US', 'AW', 'BR', 'CL', 'CO', 'EC', 'ES'} <= set(found)


def test_a_long_chinese_name_inside_a_longer_run_is_found(tmp_path):
    """A seven character Chinese name needs a wide enough n-gram window."""
    db = geo(tmp_path,
             extra_rows=[_row(24, 'Guangxi', 'CN', 'A', 'ADM1', '80', '25000000')],
             extra_aliases=['5\t24\tzh\t广西壮族自治区\n'])
    found = _by_code(retrieve_candidates(
        db, normalize_address('广西壮族自治区南宁市'), None))
    assert 'CN' in found
    assert found['CN'].support >= 0.26


def test_search_keys_are_queried_in_batches(tmp_path, monkeypatch):
    """One statement per key is what made retrieval twice as slow as needed."""
    db = geo(tmp_path)
    counter = _statement_counter(monkeypatch)
    found = retrieve_candidates(
        db,
        normalize_address('Tokyo Mumbai London Springfield Shinjuku New Delhi India Japan'),
        None)
    assert counter['n'] <= 2
    assert {'JP', 'IN', 'GB', 'US'} <= {c.destination_id for c in found}


def test_hint_candidate_never_exceeds_the_limit(tmp_path):
    db = geo(tmp_path)
    found = retrieve_candidates(
        db, normalize_address('Tokyo Mumbai London Springfield Shinjuku'), 'SG', limit=2)
    assert len(found) == 2
    assert any(c.destination_id == 'SG' for c in found)
    assert any('STRUCTURED_COUNTRY_HINT' in c.evidence for c in found)


def test_a_very_long_token_is_bounded(tmp_path):
    """A megabyte long token must not stall the retrieval."""
    db = geo(tmp_path)
    started = time.perf_counter()
    found = retrieve_candidates(db, ('x' * 1_000_000,), None)
    elapsed = time.perf_counter() - started
    assert elapsed < 5.0
    assert all(c.support == 0.0 for c in found)
    terms = retrieve_module._collect_terms(('x' * 1_000_000,))
    assert max((len(key) for keys in terms.values() for key in keys), default=0) \
        <= retrieve_module.MAX_FORM_CHARS + 1


def test_input_text_is_length_bounded():
    bounded = getattr(retrieve_module, '_bounded_segments', None)
    assert bounded is not None, 'the reader must bound the input length'
    segments = bounded('a' * 500_000)
    assert sum(len(segment) for segment in segments) <= retrieve_module.MAX_FORM_CHARS


def test_a_han_name_without_its_admin_suffix_is_still_found(tmp_path):
    """'臺北' must reach the gazetteer entry '臺北市'.

    GeoNames stores the Taiwanese and Chinese municipalities with their
    administrative suffix, while a written address often leaves it out.
    """
    rows = [
        _row(30, '臺北市', 'TW', pop=2500000),
        _row(31, '臺灣', 'TW', 'A', 'PCLI', '00', 23000000),
    ]
    found = retrieve_candidates(geo(tmp_path, extra_rows=rows),
                                normalize_address('臺北'), None)
    assert found[0].destination_id == 'TW'


def test_the_suffix_fallback_never_makes_a_known_name_ambiguous(tmp_path):
    """A name that already resolves keeps its single answer."""
    rows = [
        _row(30, '中山', 'TW', pop=210000),
        _row(31, '中山市', 'CN', pop=4500000),
    ]
    found = retrieve_candidates(geo(tmp_path, extra_rows=rows),
                                normalize_address('中山'), None)
    assert {c.destination_id for c in found} == {'TW'}


def test_the_suffix_fallback_is_not_used_for_a_plain_latin_name(tmp_path):
    """Only a Han name may be retried with an administrative suffix."""
    rows = [
        _row(30, 'Springfield', 'US', pop=170188),
        _row(31, 'Springfield City', 'CA', pop=100000),
    ]
    found = retrieve_candidates(geo(tmp_path, extra_rows=rows),
                                normalize_address('Springfield'), None)
    assert {c.destination_id for c in found} == {'US', 'CA'}
