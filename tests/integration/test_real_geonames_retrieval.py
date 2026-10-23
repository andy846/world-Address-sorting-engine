"""Retrieval behaviour against the REAL worldwide GeoNames packs.

These expectations were measured against the packs produced by GitHub Actions
run 39827512415, not against a synthetic fixture. The tests are skipped when
the packs are absent because the artefacts are far too large to commit.

The packs still carry the legacy, punctuation bearing search keys. The reader
keeps the original spelling as a second key, so a name such as "St. John's"
stays reachable; a name whose key changes with the normalisation (the comma in
"Pitcairn, Henderson, Ducie and Oeno Islands") needs the republished pack.
"""

import contextlib
import os
import time
from pathlib import Path

import pytest

from world_address_engine.matching import retrieve as retrieve_module
from world_address_engine.matching.normalize import normalize_address
from world_address_engine.matching.retrieve import retrieve_candidates
from world_address_engine.sqlite_util import open_db

REPO_ROOT = Path(__file__).resolve().parents[2]
PACK_ROOT = Path(os.environ.get("WASE_REAL_PACK_DIR",
                                REPO_ROOT / "builds" / "real-2026-10-22"))
PACKS = {
    "COMPACT_GLOBAL": PACK_ROOT / "compact" / "compact_global.sqlite",
    "EXTENDED_GLOBAL": PACK_ROOT / "extended" / "extended_global.sqlite",
}

PROFILES = sorted(PACKS)


def _pack(name):
    path = PACKS[name]
    if not path.is_file():
        pytest.skip(f"real {name} pack not present at {path}")
    return path


def _codes(found):
    return {candidate.destination_id for candidate in found}


def _by_code(found):
    return {candidate.destination_id: candidate for candidate in found}


@pytest.mark.parametrize("profile", PROFILES)
def test_a_long_official_country_name_reaches_its_own_country(profile):
    """A country name of more than four tokens must not resolve to a prefix."""
    found = _by_code(retrieve_candidates(
        _pack(profile),
        normalize_address('Wake, United States Minor Outlying Islands'), None))
    assert 'UM' in found
    assert found['UM'].country_entity is True
    assert found['UM'].support >= 0.6


@pytest.mark.parametrize("profile", PROFILES)
def test_a_country_name_of_several_words_reaches_its_own_country(profile):
    """'French Southern and Antarctic Lands' is six words long."""
    found = _by_code(retrieve_candidates(
        _pack(profile),
        normalize_address('Martin-de-Viviès, French Southern and Antarctic Lands'), None))
    assert 'TF' in found
    assert found['TF'].country_entity is True
    assert found['TF'].support >= 0.6


@pytest.mark.parametrize("profile", PROFILES)
def test_a_common_term_keeps_the_evidence_of_every_country(profile):
    """The row cap must not drop whole countries from a term."""
    geo = _pack(profile)
    found = retrieve_candidates(geo, normalize_address('Santa Rosa'), None, limit=300)
    with_term = {c.destination_id for c in found
                 if any(term == 'santa rosa' for term, _weight in c.term_support)}
    with open_db(geo) as conn:
        countries = conn.execute(
            "SELECT COUNT(DISTINCT p.country_code) FROM geo_aliases a "
            "JOIN geo_places p ON p.place_id = a.place_id "
            "WHERE a.search_key = 'santa rosa' "
            "AND (p.feature_class = 'A' OR p.population > 0)").fetchone()[0]
    assert len(with_term) == countries


@pytest.mark.parametrize("profile", PROFILES)
def test_chinese_evidence_survives_a_long_address(profile):
    """A long address must not truncate away every Chinese name."""
    long_prefix = ' '.join('word%03d' % index for index in range(120))
    found = _by_code(retrieve_candidates(
        _pack(profile), normalize_address(long_prefix + ' 香港'), None))
    assert 'HK' in found
    assert found['HK'].country_entity is True


@pytest.mark.parametrize("profile", PROFILES)
def test_a_punctuated_name_stays_reachable_in_the_legacy_pack(profile):
    """The original spelling is kept as a second key for the legacy packs."""
    found = _codes(retrieve_candidates(
        _pack(profile), normalize_address("St. John's, Newfoundland"), None))
    assert 'CA' in found


@pytest.mark.parametrize("profile", PROFILES)
def test_the_search_keys_are_queried_in_batches(profile, monkeypatch):
    """One statement per key is what made retrieval twice as slow as needed."""
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
    found = retrieve_candidates(
        _pack(profile),
        normalize_address('10 Downing Street, London SW1A 2AA, United Kingdom'),
        None)
    assert counter['n'] <= 2
    assert 'GB' in _codes(found)


@pytest.mark.parametrize("profile", PROFILES)
def test_a_very_long_input_is_bounded(profile):
    """A megabyte long token must not stall the retrieval."""
    started = time.perf_counter()
    found = retrieve_candidates(_pack(profile), ('x' * 1_000_000,), None)
    elapsed = time.perf_counter() - started
    assert elapsed < 10.0
    assert all(candidate.support == 0.0 for candidate in found)


@pytest.mark.parametrize("profile", PROFILES)
def test_the_hint_candidate_never_exceeds_the_limit(profile):
    found = retrieve_candidates(
        _pack(profile),
        normalize_address('10 Downing Street, London SW1A 2AA, United Kingdom'),
        'JP', limit=3)
    assert len(found) == 3
    assert any(candidate.destination_id == 'JP' for candidate in found)
