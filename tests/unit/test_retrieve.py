from pathlib import Path
from world_address_engine.data.geonames_builder import build_geonames_pack
from world_address_engine.matching.retrieve import retrieve_candidates
from world_address_engine.matching.normalize import normalize_address


def _row(i, name, country, fclass='P', fcode='PPL', admin1='01', pop='1000'):
    return '\t'.join([str(i), name, name, '', '0', '0', fclass, fcode, country, '', admin1,
                       '', '', '', str(pop), '', '', 'UTC', '2024-01-01'])


def geo(tmp_path):
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
    ]
    (source / 'allCountries.txt').write_text('\n'.join(rows) + '\n', encoding='utf8')
    (source / 'alternateNamesV2.txt').write_text(
        '1\t11\ten\tDelhi\n2\t13\ten\tMacau\n3\t16\tzh\t中国\n', encoding='utf8')
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
