"""Indexed, bounded retrieval of geographic destination hypotheses.

Retrieval is *evidence*, not postal delivery verification. A city name alone
must not become an asserted country in the classification layer.

Evidence mass (``support``) is reported separately from the capped
``score``. Counting matched rows saturates on a global gazetteer -- the single
token ``springfield`` matches 68 place ids in the United States and 15 in the
United Kingdom, so every candidate would reach the score ceiling -- therefore
each search term contributes at most one weight per destination, no matter how
many rows the term matches.
"""

import math
import re
from collections import defaultdict
from pathlib import Path

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
MAX_ROWS_PER_TERM = 400
MAX_TERM_TOKENS = 4
MAX_HAN_TERM_CHARS = 6
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

# The weight tier order used to truncate very common search terms. It mirrors
# the tiers of ``_row_weight`` so the highest-weight rows survive the cap.
_TIER_ORDER = """CASE WHEN p.feature_class='A' THEN
  CASE WHEN p.feature_code IN ('PCLI','PCLX','PCLS','PCLD') OR p.admin1_code='00' THEN 4
       WHEN p.feature_code='ADM1' THEN 3
       WHEN p.feature_code='ADM2' THEN 2
       ELSE 1 END
ELSE 0 END"""

_ROW_SQL = f"""
SELECT p.place_id, p.name, p.country_code, p.feature_class, p.feature_code,
       p.admin1_code, p.population
FROM geo_aliases a JOIN geo_places p ON p.place_id = a.place_id
WHERE a.search_key = ?
ORDER BY {_TIER_ORDER} DESC, p.population DESC
LIMIT {MAX_ROWS_PER_TERM}"""


def _is_noise(word: str) -> bool:
    """True for address-structure words and pure numbers."""
    return word in _ADDRESS_NOISE or word.isdigit()


def _collect_terms(forms: tuple[str, ...]) -> dict[str, set[str]]:
    """Map each canonical search term to the exact database keys it may match.

    The canonical term is the space joined token sequence; the database keys
    additionally include the original spelling, so "Timor-Leste" and
    "St. Louis" reach the aliases GeoNames actually stores.
    """
    terms: dict[str, set[str]] = {}

    def add(canonical: str, variant: str) -> None:
        terms.setdefault(canonical, set()).add(variant)

    for address in forms:
        text = address.casefold()
        tokens = [(m.group(0), m.start(), m.end()) for m in _LATIN.finditer(text)]
        for i in range(len(tokens)):
            for n in range(1, MAX_TERM_TOKENS + 1):
                if i + n > len(tokens):
                    break
                span = tokens[i:i + n]
                words = [word for word, _, _ in span]
                if len(words) == 1 and len(words[0]) < 3:
                    continue
                if all(_is_noise(word) for word in words):
                    continue
                canonical = " ".join(words)
                add(canonical, canonical)
                sliced = " ".join(text[span[0][1]:span[-1][2]].split())
                if sliced and sliced != canonical:
                    add(canonical, sliced)
        for match in _HAN.finditer(text):
            run = match.group(0)
            add(run, run)
            for i in range(len(run)):
                for n in range(2, MAX_HAN_TERM_CHARS + 1):
                    if i + n > len(run):
                        break
                    add(run[i:i + n], run[i:i + n])
    return terms


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


def retrieve_candidates(geo_db: Path, address_forms: tuple[str, ...],
                        country_hint: str | None = None, limit: int = 20) -> list[DestinationCandidate]:
    """Return bounded destination hypotheses for the supplied address forms.

    ``support`` is the explainable evidence mass of a destination and
    ``token_count`` the number of distinct search terms that contributed to
    it. A destination is only a candidate hypothesis; deciding whether it may
    be asserted is the classifier's job.
    """
    if limit < 1:
        return []
    terms = _collect_terms(address_forms)
    if len(terms) > MAX_TERMS:
        terms = dict(list(terms.items())[:MAX_TERMS])

    # place_id -> (weight, name, country, feature_class)
    place_rows: dict[int, tuple[float, str, str, str]] = {}
    # place_id -> longest canonical term that matched it
    place_terms: dict[int, str] = {}
    # canonical term -> database key
    form_owner: dict[str, str] = {}

    with open_db(geo_db) as db:
        for canonical, variants in terms.items():
            for variant in variants:
                form_owner.setdefault(variant, canonical)
        for variant, canonical in form_owner.items():
            for row in db.execute(_ROW_SQL, (variant,)):
                place_id, name, country, feature_class, feature_code, admin1, population = row
                weight = _row_weight(feature_class, feature_code, admin1, population or 0)
                if weight <= 0.0:
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
    results = results[:limit]

    if country_hint and re.fullmatch(r"[A-Za-z]{2}", country_hint.strip()):
        code = country_hint.strip().upper()
        hinted = next((c for c in results if c.destination_id == code), None)
        if hinted is None:
            results.append(DestinationCandidate(
                code, ("STRUCTURED_COUNTRY_HINT",), 0.0, support=0.0))
        elif "STRUCTURED_COUNTRY_HINT" not in hinted.evidence:
            results[results.index(hinted)] = DestinationCandidate(
                hinted.destination_id,
                ("STRUCTURED_COUNTRY_HINT",) + hinted.evidence,
                hinted.score, hinted.support, hinted.token_count,
                hinted.country_entity, hinted.entity_terms, hinted.term_support)
    return results
