"""Indexed, bounded retrieval of geographic destination hypotheses.

Retrieval is *evidence*, not postal delivery verification. A city name alone
must not become an asserted country in the classification layer.

Evidence mass (``support``) is reported separately from the capped
``score``. Counting matched rows saturates on a global gazetteer -- the single
token ``springfield`` matches 68 place ids in the United States and 15 in the
United Kingdom, so every candidate would reach the score ceiling -- therefore
each search term contributes at most one weight per destination, no matter how
many rows the term matches.

Search keys are produced by ``data.geonames_builder.normalize_search_key``, so
the reader and the pack always agree on one spelling of a name.
"""

import math
import re
import unicodedata
from collections import defaultdict
from pathlib import Path

from world_address_engine.data.geonames_builder import normalize_search_key
from world_address_engine.models import DestinationCandidate
from world_address_engine.sqlite_util import open_db

# Latin letters with diacritics plus digits. Han is handled separately.
_LATIN = re.compile(r"[a-z\u00c0-\u024f\u1e00-\u1eff0-9]+")
_HAN = re.compile(r"[\u3400-\u9fff]+")

COUNTRY_ENTITY_WEIGHT = 0.60
ADMIN1_WEIGHT = 0.26
ADMIN2_WEIGHT = 0.16
ADMIN_DEEP_WEIGHT = 0.08
POPULATED_WEIGHT = 0.26
POPULATION_SCALE = 6.0

# A destination needs at least this much evidence mass to be considered at all.
MIN_SUPPORT = 0.15

MAX_TERMS = 384
# Official country names are long: "United States Minor Outlying Islands" or
# "Pitcairn, Henderson, Ducie and Oeno Islands". Four tokens could never reach
# them, and the pack then resolved the prefix to a different country.
MAX_TERM_TOKENS = 8
# Chinese names carry no separators, so a long name sits inside a longer run.
MAX_HAN_TERM_CHARS = 11
# Bounds for hostile or generated input.
MAX_FORM_CHARS = 10_000
MAX_FORM_TOKENS = 256
MAX_HAN_RUN_CHARS = 48
# Fairness: a term keeps the best row of every country it mentions.
MAX_COUNTRIES_PER_TERM = 64
# Keys are queried in batches, so a record costs a handful of statements.
QUERY_KEY_CHUNK = 200
MAX_EVIDENCE_ENTRIES = 20

COUNTRY_FEATURE_CODES = frozenset({"PCLI", "PCLX", "PCLS", "PCLD"})

# Address structure words are never geographic evidence on their own. A
# multi-word place name that merely contains one of them ("Hyde Park") is
# still searchable because a term is only dropped when *every* token is noise.
_ADDRESS_NOISE = frozenset({
    "main", "street", "road", "avenue", "lane", "drive", "boulevard", "terrace",
    "court", "place", "square", "plaza", "floor", "suite", "unit", "room",
    "building", "tower", "block", "number", "no", "the", "and", "of", "in",
    "at", "on", "to", "for", "near", "by", "with", "from", "against",
    "postal", "postcode", "zip", "code", "area", "district", "centre", "center",
    "park", "village", "town", "city", "county", "state", "province", "region",
    "close", "crescent", "mews", "parade", "grove", "gardens", "hill", "view",
    "rise", "vale", "wharf", "yard", "row", "quay", "apartment", "apt", "flat",
    "dept", "department", "ministry", "embassy", "consulate", "hospital",
    "hotel", "airport", "station", "bridge", "gate", "industrial", "commercial",
    "residential", "general", "head", "central", "front", "rear", "upper",
    "lower", "new", "old", "port", "mount", "fort", "royal", "p.o", "box",
})

# The rows of one search key are ranked by the weight they carry, not by their
# feature class, so that the best row of a country is kept even when another
# row of the same country scores higher. The populated weight grows with the
# population, so a populated place outranks an administrative row once it is
# large enough; the bands below reproduce that order exactly.
_ADMIN_RANKS = {"entity": 90, "adm1": 80, "adm2": 70, "deep": 60}
_POPULATED_RANKS = {"adm1": 85, "adm2": 75, "deep": 65, "any": 55}


def _population_threshold(weight: float) -> int:
    """Smallest population whose populated weight reaches ``weight``."""
    return math.ceil(10 ** (weight * POPULATION_SCALE / POPULATED_WEIGHT)) - 1


_WEIGHT_RANK_EXPRESSION = f"""CASE WHEN p.feature_class='A' THEN
  CASE WHEN p.feature_code IN ('PCLI','PCLX','PCLS','PCLD') OR p.admin1_code='00'
       THEN {_ADMIN_RANKS['entity']}
       WHEN p.feature_code='ADM1' THEN {_ADMIN_RANKS['adm1']}
       WHEN p.feature_code='ADM2' THEN {_ADMIN_RANKS['adm2']}
       ELSE {_ADMIN_RANKS['deep']} END
ELSE CASE WHEN p.population >= {_population_threshold(ADMIN1_WEIGHT)}
       THEN {_POPULATED_RANKS['adm1']}
      WHEN p.population >= {_population_threshold(ADMIN2_WEIGHT)}
       THEN {_POPULATED_RANKS['adm2']}
      WHEN p.population >= {_population_threshold(ADMIN_DEEP_WEIGHT)}
       THEN {_POPULATED_RANKS['deep']}
      WHEN p.population >= 1 THEN {_POPULATED_RANKS['any']}
      ELSE 0 END END"""

# One statement per batch of search keys. The window function keeps the best
# row of every (key, country) pair, so a term that matches thousands of
# places still reports each country it mentions instead of only the first
# rows, and a record costs a couple of statements instead of one per key.
_ROW_SQL = f"""
WITH matched AS (
  SELECT a.search_key AS search_key, p.place_id AS place_id, p.name AS name,
         p.country_code AS country_code, p.feature_class AS feature_class,
         p.feature_code AS feature_code, p.admin1_code AS admin1_code,
         p.population AS population, {_WEIGHT_RANK_EXPRESSION} AS weight_rank
  FROM geo_aliases a JOIN geo_places p ON p.place_id = a.place_id
  WHERE a.search_key IN ({{placeholders}})
),
ranked AS (
  SELECT matched.*, ROW_NUMBER() OVER (
      PARTITION BY search_key, country_code
      ORDER BY weight_rank DESC, population DESC, place_id ASC) AS country_rank
  FROM matched
)
SELECT search_key, place_id, name, country_code, feature_class, feature_code,
       admin1_code, population
FROM ranked
WHERE country_rank = 1
ORDER BY search_key, weight_rank DESC, population DESC, country_code"""


def _is_noise(word: str) -> bool:
    """True for address-structure words and pure numbers."""
    return word in _ADDRESS_NOISE or word.isdigit()


def _is_han_term(term: str) -> bool:
    """True when a search term contains a Han character."""
    return any("\u3400" <= char <= "\u9fff" for char in term)


def _bounded_segments(address: str) -> tuple[str, ...]:
    """Normalise one address form and bound its length.

    Hostile or generated input can be arbitrarily long. The head and the tail
    are kept as separate segments, because the tail of an address usually
    carries the country. The segments are never joined, so a search term can
    not span the cut.
    """
    text = unicodedata.normalize("NFKC", address).casefold()
    if len(text) <= MAX_FORM_CHARS:
        return (text,)
    half = MAX_FORM_CHARS // 2
    return (text[:half], text[-half:])


def _collect_terms(forms: tuple[str, ...]) -> dict[str, set[str]]:
    """Map each canonical search term to the exact database keys it may match.

    The canonical term is the space joined token sequence; the database keys
    additionally include the original spelling, so "Timor-Leste" and
    "St. Louis" reach the aliases GeoNames actually stores. The canonical key
    itself is punctuation free, exactly like the keys a current pack stores.
    """
    terms: dict[str, set[str]] = {}

    def add(canonical: str, key: str) -> None:
        terms.setdefault(canonical, set()).add(key)

    for address in forms:
        for text in _bounded_segments(address):
            tokens = [(m.group(0), m.start(), m.end()) for m in _LATIN.finditer(text)]
            groups = [tokens]
            if len(tokens) > MAX_FORM_TOKENS:
                head = MAX_FORM_TOKENS // 2
                groups = [tokens[:head], tokens[-(MAX_FORM_TOKENS - head):]]
            for group in groups:
                for i in range(len(group)):
                    for n in range(1, MAX_TERM_TOKENS + 1):
                        if i + n > len(group):
                            break
                        span = group[i:i + n]
                        words = [word for word, _, _ in span]
                        if len(words) == 1 and len(words[0]) < 3:
                            continue
                        if all(_is_noise(word) for word in words):
                            continue
                        canonical = " ".join(words)
                        add(canonical, normalize_search_key(canonical))
                        spelling = " ".join(text[span[0][1]:span[-1][2]].split())
                        if spelling and spelling != canonical:
                            add(canonical, spelling)
            for match in _HAN.finditer(text):
                run = match.group(0)
                add(run, run)
                # A very long run is cut for n-gram generation only; the run
                # stays one canonical term. Every n-gram is a term of its own,
                # so a place that answers to two names keeps both
                # contributions.
                pieces = [run]
                if len(run) > MAX_HAN_RUN_CHARS:
                    half = MAX_HAN_RUN_CHARS // 2
                    pieces = [run[:half], run[-half:]]
                for piece in pieces:
                    for i in range(len(piece)):
                        for n in range(2, MAX_HAN_TERM_CHARS + 1):
                            if i + n > len(piece):
                                break
                            add(piece[i:i + n], piece[i:i + n])
    return terms


def _truncate_terms(terms: dict[str, set[str]]) -> dict[str, set[str]]:
    """Keep the evidence budget without ever losing a whole script.

    Latin terms are generated before Han terms, so a plain head truncation
    dropped every Chinese name from a long address. The two scripts are
    interleaved instead, which keeps the budget while guaranteeing that both
    survive.
    """
    if len(terms) <= MAX_TERMS:
        return terms
    han = [(key, value) for key, value in terms.items() if _is_han_term(key)]
    other = [(key, value) for key, value in terms.items() if not _is_han_term(key)]
    kept: dict[str, set[str]] = {}
    for index in range(max(len(han), len(other))):
        for group in (other, han):
            if index < len(group) and len(kept) < MAX_TERMS:
                kept[group[index][0]] = group[index][1]
        if len(kept) >= MAX_TERMS:
            break
    return kept


def _prominence(population: int) -> float:
    """Scale a population to [0, 1]; a place with no residents carries none."""
    if population <= 0:
        return 0.0
    return min(1.0, math.log10(population + 1) / POPULATION_SCALE)


def _row_weight(feature_class: str, feature_code: str, admin1_code: str, population: int) -> float:
    """Weight of a single gazetteer row."""
    if feature_class == "A":
        if feature_code in COUNTRY_FEATURE_CODES or admin1_code == "00":
            return COUNTRY_ENTITY_WEIGHT
        if feature_code == "ADM1":
            return ADMIN1_WEIGHT
        if feature_code == "ADM2":
            return ADMIN2_WEIGHT
        return ADMIN_DEEP_WEIGHT
    return POPULATED_WEIGHT * _prominence(population)


def _chunked(items: list[str], size: int):
    """Split a key list into batches that fit one SQL statement."""
    for start in range(0, len(items), size):
        yield items[start:start + size]


def retrieve_candidates(geo_db: Path, address_forms: tuple[str, ...],
                        country_hint: str | None = None, limit: int = 20) -> list[DestinationCandidate]:
    """Return bounded destination hypotheses for the supplied address forms.

    ``support`` is the explainable evidence mass of a destination and
    ``token_count`` the number of distinct search terms that contributed to
    it. A destination is only a candidate hypothesis; deciding whether it may
    be asserted is the classifier's job.

    The result never holds more than ``limit`` candidates. A structured
    country hint is always reported, so it displaces the weakest geographic
    hypothesis when the budget is exhausted.
    """
    if limit < 1:
        return []
    terms = _truncate_terms(_collect_terms(address_forms))

    # database key -> the canonical term that owns it
    key_owner: dict[str, str] = {}
    for canonical, variants in terms.items():
        for variant in variants:
            key_owner.setdefault(variant, canonical)

    # place_id -> (weight, name, country, feature_class)
    place_rows: dict[int, tuple[float, str, str, str]] = {}
    # place_id -> longest canonical term that matched it
    place_terms: dict[int, str] = {}

    with open_db(geo_db) as db:
        for chunk in _chunked(list(key_owner), QUERY_KEY_CHUNK):
            statement = _ROW_SQL.format(placeholders=",".join("?" * len(chunk)))
            per_key: dict[str, int] = defaultdict(int)
            for row in db.execute(statement, chunk):
                search_key = row[0]
                if per_key[search_key] >= MAX_COUNTRIES_PER_TERM:
                    continue
                per_key[search_key] += 1
                place_id, name, country, feature_class, feature_code, admin1, population = row[1:]
                weight = _row_weight(feature_class, feature_code, admin1, population or 0)
                if weight <= 0.0:
                    continue
                canonical = key_owner.get(search_key)
                if canonical is None:
                    continue
                current = place_rows.get(place_id)
                if current is None or weight > current[0]:
                    place_rows[place_id] = (weight, name, country, feature_class)
                known = place_terms.get(place_id)
                if known is None or len(canonical) > len(known):
                    place_terms[place_id] = canonical

    # (canonical term, country) -> (weight, place_id)
    buckets: dict[tuple[str, str], tuple[float, int]] = {}
    for place_id, (weight, _name, country, _cls) in place_rows.items():
        canonical = place_terms.get(place_id)
        if canonical is None:
            continue
        key = (canonical, country)
        current = buckets.get(key)
        if current is None or weight > current[0]:
            buckets[key] = (weight, place_id)

    per_country: dict[str, dict[str, tuple[float, int]]] = defaultdict(dict)
    for (canonical, country), value in buckets.items():
        per_country[country][canonical] = value

    results: list[DestinationCandidate] = []
    for country, contributions in per_country.items():
        support = 0.0
        entity_terms: list[str] = []
        for canonical, (weight, place_id) in contributions.items():
            support += weight
            if weight >= COUNTRY_ENTITY_WEIGHT:
                entity_terms.append(canonical)
        evidence: list[str] = []
        for canonical, (_weight, place_id) in sorted(
                contributions.items(), key=lambda item: (-item[1][0], item[0])):
            _weight, name, _country, feature_class = place_rows[place_id]
            entry = f"PLACE:{place_id}:{name}:{feature_class}"
            if entry not in evidence:
                evidence.append(entry)
            if len(evidence) >= MAX_EVIDENCE_ENTRIES:
                break
        results.append(DestinationCandidate(
            country,
            tuple(evidence),
            min(0.99, support),
            support=support,
            token_count=len(contributions),
            country_entity=bool(entity_terms),
            entity_terms=tuple(sorted(entity_terms)),
            term_support=tuple(sorted(
                ((canonical, weight) for canonical, (weight, _) in contributions.items()),
                key=lambda item: (-item[1], item[0]))),
        ))

    results.sort(key=lambda c: (-c.support, c.destination_id))

    if country_hint and re.fullmatch(r"[A-Za-z]{2}", country_hint.strip()):
        code = country_hint.strip().upper()
        hinted = next((c for c in results if c.destination_id == code), None)
        if hinted is None:
            hint = DestinationCandidate(
                code, ("STRUCTURED_COUNTRY_HINT",), 0.0, support=0.0)
            if len(results) >= limit:
                # The hint is structured input, so it displaces the weakest
                # geographic hypothesis instead of exceeding the bound.
                results[limit - 1] = hint
            else:
                results.append(hint)
        elif "STRUCTURED_COUNTRY_HINT" not in hinted.evidence:
            results[results.index(hinted)] = DestinationCandidate(
                hinted.destination_id,
                ("STRUCTURED_COUNTRY_HINT",) + hinted.evidence,
                hinted.score, hinted.support, hinted.token_count,
                hinted.country_entity, hinted.entity_terms, hinted.term_support)
    return results[:limit]
