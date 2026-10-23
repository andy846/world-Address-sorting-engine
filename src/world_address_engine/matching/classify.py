"""Conservative address-to-Hongkong-Post code decision engine (offline).

Only reviewed HKP_DESTINATION_2 codes may be output, never ISO fallbacks.
The confidence value is a heuristic, NOT calibrated postal accuracy.

Three failure modes are treated as first-class defects rather than tuning
problems:

* a country that only appears inside a company name ("CHINA CONSTRUCTION LTD")
  is not geographic evidence;
* a lone city token is not a destination, so a springfield cannot pick a
  country out of the gazetteer;
* a structured country field that contradicts the address text is a conflict,
  not a licence to emit the supplied country.
"""

import re
import unicodedata
from bisect import bisect_left, bisect_right
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from world_address_engine.hkp.approval import CatalogueApproval
from world_address_engine.models import AddressRecord, ClassificationResult
from world_address_engine.matching.normalize import (
    contains_keyed, has_unsupported_script, normalize_address, normalize_key,
)
from world_address_engine.matching.retrieve import (
    COUNTRY_FEATURE_CODES, HAN_ADMIN_SUFFIXES, MAX_OCCURRENCES, MIN_SUPPORT,
    PLACE_CONTEXT_MIN_WEIGHT, OccurrenceLimitExceeded, _SpanIndex,
    _is_name_separator,
    _is_sovereign_country_expansion, _is_sovereign_country_prefix,
    _term_spans, retrieve_candidates,
)
from world_address_engine.sqlite_util import open_db

CODE_RE = re.compile(r"[A-Z]{2}")
# Review the complete record rather than silently classifying a truncated tail.
MAX_ADDRESS_CHARS = 10_000

# A rival destination within this share of the leader's evidence is a real
# alternative, not noise.
RIVAL_RATIO = 0.55

# A destination is only assertable when at least one term carries real
# weight: a country entity, an administrative area or a populated place of
# meaningful size. Two insignificant places are not a country.
STRONG_TERM = 0.16

# How far from the matched name a company marker still counts as adjacent.
MARKER_WINDOW = 4
MARKER_CHARS = 6

LATIN_STRONG_MARKERS = frozenset({
    "ltd", "limited", "ltda", "plc", "inc", "incorporated", "llc", "llp",
    "corp", "corporation", "gmbh", "company", "holdings", "holding",
    "group", "enterprises", "industries", "trading", "logistics", "bank",
    "agency", "ventures", "partners", "foundation", "association",
    "institute", "investors", "sdn", "bhd", "pte",
    "telecom", "telecommunications", "communications", "airlines", "airways",
    "media", "networks", "systems",
})
LATIN_WEAK_MARKERS = frozenset({
    "international", "services", "service", "industry", "express",
    "technology", "technologies", "solutions", "consultants", "contractors",
    "engineering", "investment", "capital", "realty", "estate", "estates",
    "works", "mills", "factory", "factories", "distributors", "wholesale",
    "retail", "enterprise", "constructions", "management", "consulting",
})
HAN_STRONG_MARKERS = (
    "有限公司", "集團", "集团", "銀行", "银行", "公司", "股份", "實業", "实业",
    "控股", "企業", "企业",
)
HAN_WEAK_MARKERS = (
    "國際", "国际", "貿易", "贸易", "商貿", "商贸", "物流", "科技", "投資",
    "投资", "製造", "制造", "運輸", "运输", "電子", "电子", "化工", "機械",
    "机械", "建設", "建设", "發展", "发展", "進出口", "进出口",
)

# A legal-form marker shorter than three characters is never a company
# suffix: "CO" is the US state postal code for Colorado, and a bare "co"
# appears inside names such as "Co-operative Republic of Guyana".
MARKER_MIN_LENGTH = 3

# Words that join a place name to its qualifier ("Republic OF China") and
# therefore must not make the preceding word look like a company name.
TRAILING_EXEMPT = frozenset({
    "of", "the", "and", "de", "del", "della", "di", "da", "du", "des",
    "la", "le", "van", "von", "al", "el", "bin", "ibn",
})

_FRAGMENT_SPLIT = re.compile(r"[,;:\n\r，；、。]+")
_WORD = re.compile(r"[A-Za-z0-9\u00c0-\u024f\u1e00-\u1eff]+")

# The catalogue is re-read for every record otherwise. The cache key binds
# the file identity and the approval that governs it.
_CATALOGUE_CACHE: dict[tuple, "_Catalogue"] = {}


@dataclass(frozen=True)
class _Catalogue:
    """The approved HKP master and its ISO crosswalk."""

    destination_codes: dict[str, str] = field(default_factory=dict)
    destination_iso: dict[str, str] = field(default_factory=dict)
    iso_to_destination: dict[str, str] = field(default_factory=dict)
    names_by_iso: dict[str, tuple[str, ...]] = field(default_factory=dict)
    names_by_destination: dict[str, tuple[str, ...]] = field(default_factory=dict)


def _catalogue(path: Path, approval: CatalogueApproval | None = None) -> _Catalogue:
    """Read the approved catalogue and reject anything not fit to assert.

    A code that is not two uppercase letters is never emitted, and an ISO
    code claimed by more than one destination is never resolved. The catalogue
    file is data, not authority: a code is only resolvable when a verified
    approval ratifies the destination and the official document it came from.
    """
    key = None
    try:
        stat = Path(path).stat()
        key = (str(Path(path).resolve()), stat.st_mtime_ns, stat.st_size,
               approval.approval_id if approval else None,
               approval.manifest_sha256 if approval else None)
    except OSError:
        key = None
    cached = _CATALOGUE_CACHE.get(key) if key is not None else None
    if cached is not None:
        return cached
    with open_db(path) as db:
        rows = db.execute("""SELECT destination_id,code,name_en,name_zh_hant,name_zh_hans,
                              source_url,source_doc_version,source_checksum
                              FROM destinations WHERE code_scheme='HKP_DESTINATION_2'
                              AND profile='HKP_DESTINATION_2' AND approval_status='APPROVED' """).fetchall()
        iso_rows = db.execute("""SELECT code,destination_id FROM destinations
                                 WHERE code_scheme='ISO_ALPHA2' AND profile='ISO'
                                 AND approval_status='APPROVED' """).fetchall()
    destination_codes: dict[str, str] = {}
    names_by_destination: dict[str, tuple[str, ...]] = {}
    for (destination_id, code, name_en, name_tc, name_sc,
         source_url, source_doc_version, source_checksum) in rows:
        if not code or not CODE_RE.fullmatch(code):
            continue
        if approval is not None and approval.allows(destination_id) and approval.ratifies_source(
                source_url=source_url or "", source_doc_version=source_doc_version or "",
                source_checksum=source_checksum or ""):
            destination_codes[destination_id] = code
        names_by_destination[destination_id] = (name_en or "", name_tc or "", name_sc or "")
    iso_to_destination: dict[str, str] = {}
    ambiguous: set[str] = set()
    for code, destination_id in iso_rows:
        if not code or not CODE_RE.fullmatch(code):
            continue
        if code in iso_to_destination and iso_to_destination[code] != destination_id:
            ambiguous.add(code)
        else:
            iso_to_destination[code] = destination_id
    for code in ambiguous:
        iso_to_destination.pop(code, None)
    destination_iso = {destination_id: code for code, destination_id in iso_to_destination.items()}
    names_by_iso = {
        destination_iso[destination_id]: names
        for destination_id, names in names_by_destination.items()
        if destination_id in destination_iso
    }
    catalogue = _Catalogue(destination_codes, destination_iso, iso_to_destination,
                           names_by_iso, names_by_destination)
    if key is not None:
        if len(_CATALOGUE_CACHE) >= 8:
            _CATALOGUE_CACHE.clear()
        _CATALOGUE_CACHE[key] = catalogue
    return catalogue


def _is_han(text: str) -> bool:
    return any("\u3400" <= char <= "\u9fff" for char in text)


def _fragments(text: str) -> list[tuple[str, int]]:
    """Split on separators that end a company or place phrase."""
    parts: list[tuple[str, int]] = []
    start = 0
    for match in _FRAGMENT_SPLIT.finditer(text):
        parts.append((text[start:match.start()], start))
        start = match.end()
    parts.append((text[start:], start))
    return parts


def _latin_marker_near(chunk: str, words, first: int, last: int,
                       eligible=None, has_strong=None) -> bool:
    """True when a legal-form marker sits beside the matched phrase."""
    if eligible is None:
        eligible = {index: word.casefold() for index, (word, _start, end) in enumerate(words)
                    if len(word) >= MARKER_MIN_LENGTH and chunk[end:end + 1] != '-'}
    low = max(0, first - MARKER_WINDOW)
    high = min(len(words) - 1, last + MARKER_WINDOW)
    nearby = [eligible[i] for i in range(low, high + 1) if i in eligible]
    if any(token in LATIN_STRONG_MARKERS for token in nearby):
        return True
    if any(token in LATIN_WEAK_MARKERS for token in nearby):
        return has_strong if has_strong is not None else any(
            token in LATIN_STRONG_MARKERS for token in eligible.values())
    return False


def _han_marker_near(chunk: str, index: int, length: int) -> bool:
    before = chunk[max(0, index - MARKER_CHARS):index]
    after = chunk[index + length:index + length + MARKER_CHARS]
    if any(marker in before or marker in after for marker in HAN_STRONG_MARKERS):
        return True
    if any(marker in before or marker in after for marker in HAN_WEAK_MARKERS):
        return any(marker in chunk for marker in HAN_STRONG_MARKERS)
    return False


@dataclass
class _Occurrence:
    """One located name plus the fragment context needed to review it."""

    start: int
    end: int
    company: bool
    context_key: tuple[int, int]
    first: int | None
    last: int | None
    han: bool
    term: str


def _address_like_prefix(words) -> bool:
    """True for state/postal structure such as ``NY`` or ``CO 80202``."""
    tokens = [word.casefold() for word in words]
    if not tokens or not all(
            token.isdigit() or (token.isalpha() and len(token) <= 2)
            for token in tokens):
        return False
    return any(token.isdigit() for token in tokens) or all(
        token.isalpha() and len(token) == 2 for token in tokens)


def _scan_left(scope: str, left: int, position: int, *, han: bool) -> int:
    """Move left across separators and, for Han, administrative suffixes."""
    while position > left:
        char = scope[position - 1]
        if _is_name_separator(char) or (han and char in HAN_ADMIN_SUFFIXES):
            position -= 1
            continue
        break
    return position


def _scan_right(scope: str, right: int, position: int, *, han: bool) -> int:
    """Move right across separators and, for Han, administrative suffixes."""
    while position < right:
        char = scope[position]
        if _is_name_separator(char) or (han and char in HAN_ADMIN_SUFFIXES):
            position += 1
            continue
        break
    return position


def _neighbor_is_geographic(edge, spans_by_edge) -> bool:
    """True when a strong geographic span ends or starts at ``edge``."""
    return edge in spans_by_edge


def _same_country_neighbour(edge, countries_by_edge, own_countries) -> bool:
    """True when the adjacent word names a place of the same country.

    A settlement of the country is geographic context even when its own
    weight is below the assertion threshold, so "Bearna Ireland" is an
    address chain rather than a company name. The neighbour must be
    substantial: a hamlet of a few hundred people, such as the commune
    "Target" in France, is as likely to be an ordinary word that happens to
    be a place name, and treating it as context would turn "France Target"
    into an asserted destination.
    """
    if not own_countries:
        return False
    neighbour = countries_by_edge.get(edge)
    return bool(neighbour) and bool(neighbour & own_countries)


def _structural_company(occurrence: _Occurrence, scope: str, contexts,
                        latin_by_start, latin_by_end,
                        han_by_start, han_by_end,
                        substantial_end_countries, substantial_start_countries,
                        entity_countries) -> bool:
    """Return whether adjacent non-geographic text makes a use a brand."""
    left, right = occurrence.context_key
    own_countries = entity_countries.get(occurrence.term, frozenset())
    if occurrence.han:
        before = _scan_left(scope, left, occurrence.start, han=True)
        after = _scan_right(scope, right, occurrence.end, han=True)
        before_ok = (before == left
                     or _neighbor_is_geographic(before, han_by_end))
        after_ok = (after == right
                    or _neighbor_is_geographic(after, han_by_start))
        return not (before_ok and after_ok)

    words, starts, ends, _eligible, _has_strong = contexts[occurrence.context_key]
    first = occurrence.first
    last = occurrence.last
    if first is None or last is None:
        return False

    leading_company = False
    if first > 0:
        edge = _scan_left(scope, left, occurrence.start, han=False)
        prefix = [word for word, _start, _end in words[:first]]
        leading_company = not (
            _neighbor_is_geographic(edge, latin_by_end)
            or _same_country_neighbour(
                edge, substantial_end_countries, own_countries)
            or _address_like_prefix(prefix)
            or _is_sovereign_country_prefix(prefix)
        )

    trailing_company = False
    if last + 1 < len(words):
        following = words[last + 1][0]
        edge = _scan_right(scope, right, occurrence.end, han=False)
        has_digit = any(char.isdigit() for char in following)
        trailing_company = not (
            has_digit
            or following.casefold() in TRAILING_EXEMPT
            or _neighbor_is_geographic(edge, latin_by_start)
            or _same_country_neighbour(
                edge, substantial_start_countries, own_countries)
            or (following.isalpha() and len(following) <= 2)
        )
    return leading_company or trailing_company


def _strong_geographic_spans(candidates, occurrences) -> set[tuple[int, int]]:
    """Spans that may legitimately introduce or follow another place name."""
    return {
        (occurrence.start, occurrence.end)
        for candidate in candidates
        for term, weight in candidate.term_support
        if weight >= MIN_SUPPORT or term in candidate.entity_terms
        for occurrence in occurrences[term]
        if not occurrence.company
    }


def _candidate_geographic_spans(candidates, occurrences) -> set[tuple[int, int]]:
    """Every located candidate span, including deep Han administrative names."""
    return {
        (occurrence.start, occurrence.end)
        for candidate in candidates
        for term, _weight in candidate.term_support
        for occurrence in occurrences[term]
    }


def _refine_occurrence_context(scope: str, candidates, occurrences, contexts,
                               substantial_end_countries, substantial_start_countries,
                               entity_countries) -> None:
    """Resolve leading/trailing brand context against known geography.

    Strong spans can themselves become company context, so recompute until the
    set stops shrinking. The loop is bounded because a span can only move from
    independent to company, never back.
    """
    unique = {}
    for uses in occurrences.values():
        for occurrence in uses:
            unique[id(occurrence)] = occurrence
    for _ in range(3):
        latin_spans = _strong_geographic_spans(candidates, occurrences)
        han_spans = _candidate_geographic_spans(candidates, occurrences)
        latin_by_start = {start for start, _end in latin_spans}
        latin_by_end = {end for _start, end in latin_spans}
        han_by_start = {start for start, _end in han_spans}
        han_by_end = {end for _start, end in han_spans}
        changed = False
        for occurrence in unique.values():
            if occurrence.company:
                continue
            company = _structural_company(
                occurrence, scope, contexts,
                latin_by_start, latin_by_end, han_by_start, han_by_end,
                substantial_end_countries, substantial_start_countries, entity_countries)
            if company:
                occurrence.company = True
                changed = True
        if not changed:
            return


def _country_maps(candidates):
    """Map every candidate term to the countries that claim it."""
    term_countries: dict[str, set[str]] = {}
    entity_countries: dict[str, set[str]] = {}
    sovereign_terms: set[str] = set()
    substantial_countries: dict[str, set[str]] = {}
    for candidate in candidates:
        for term, weight in candidate.term_support:
            term_countries.setdefault(term, set()).add(candidate.destination_id)
            # Only a substantial place may act as the geographic context of
            # its own country: a hamlet of a few hundred people is as likely
            # to be an ordinary word that happens to be a place name.
            if weight >= PLACE_CONTEXT_MIN_WEIGHT:
                substantial_countries.setdefault(term, set()).add(
                    candidate.destination_id)
        for term in candidate.entity_terms:
            entity_countries.setdefault(term, set()).add(candidate.destination_id)
        for term, feature_code in candidate.entity_feature_codes:
            if feature_code in COUNTRY_FEATURE_CODES:
                sovereign_terms.add(term)
    return (term_countries, entity_countries, sovereign_terms,
            substantial_countries)


def _neighbour_index(occurrences, term_countries):
    """Index the countries and the names that touch every word edge."""
    end_countries: dict[int, set[str]] = {}
    start_countries: dict[int, set[str]] = {}
    end_terms: dict[int, set[str]] = {}
    start_terms: dict[int, set[str]] = {}
    for term, uses in occurrences.items():
        countries = term_countries.get(term)
        if not countries:
            continue
        for use in uses:
            end_countries.setdefault(use.end, set()).update(countries)
            start_countries.setdefault(use.start, set()).update(countries)
            end_terms.setdefault(use.end, set()).add(term)
            start_terms.setdefault(use.start, set()).add(term)
    return end_countries, start_countries, end_terms, start_terms


def _occurrence_edges(occurrence, scope, contexts):
    """Return the word edges that touch a Latin occurrence."""
    if occurrence.han or occurrence.first is None or occurrence.last is None:
        return None, None
    left, right = occurrence.context_key
    words = contexts[occurrence.context_key][0]
    left_edge = None
    right_edge = None
    if occurrence.first > 0:
        left_edge = _scan_left(scope, left, occurrence.start, han=False)
    if occurrence.last + 1 < len(words):
        right_edge = _scan_right(scope, right, occurrence.end, han=False)
    return left_edge, right_edge


def _other_country_evidence(term, own_countries, occurrences, term_countries):
    """True when another name in the address supports the same country."""
    for other, uses in occurrences.items():
        if other == term:
            continue
        countries = term_countries.get(other)
        if not countries or not (countries & own_countries):
            continue
        if any(not use.company for use in uses):
            return True
    return False


def _touching_occurrences(all_occurrences):
    """Index the occurrences that touch a Han name without a separator."""
    starts_at: dict[int, list[_Occurrence]] = {}
    ends_at: dict[int, list[_Occurrence]] = {}
    for occurrence in all_occurrences:
        starts_at.setdefault(occurrence.start, []).append(occurrence)
        ends_at.setdefault(occurrence.end, []).append(occurrence)
    return starts_at, ends_at


def _han_brand(occurrence, touching, term_countries, sovereign_terms,
               own_countries) -> bool:
    """True when a Han country name modifies a place of another country.

    Chinese writes a country name and a foreign place name without any
    separator, so "中国東京" is as much a brand as "China Mobile" is in
    Latin. A country name next to another country stays a conflict.
    """
    starts_at, ends_at = touching
    neighbours = list(starts_at.get(occurrence.end, ()))
    neighbours.extend(ends_at.get(occurrence.start, ()))
    for neighbour in neighbours:
        if neighbour is occurrence:
            continue
        countries = term_countries.get(neighbour.term)
        if not countries or (countries & own_countries):
            continue
        if neighbour.term in sovereign_terms:
            continue
        return True
    return False


def _mark_brand_country_entities(scope, occurrences, contexts, term_countries,
                                 entity_countries, sovereign_terms,
                                 end_countries, start_countries, end_terms,
                                 start_terms, all_occurrences) -> None:
    """Withdraw a country name that only modifies a foreign place name.

    "China Mobile" is a company name, not an address in China. The country
    name stands directly next to a place of another country without a
    separator, and nothing else in the address supports that country, so the
    country name is brand context rather than geographic evidence. A country
    name next to another country is a conflict, not a brand, and is left to
    the explicit-conflict policy.
    """
    touching = _touching_occurrences(all_occurrences)
    for term, uses in occurrences.items():
        own_countries = entity_countries.get(term)
        if not own_countries:
            continue
        for use in uses:
            if use.company:
                continue
            if _other_country_evidence(term, own_countries, occurrences,
                                       term_countries):
                continue
            if use.han:
                if _han_brand(use, touching, term_countries, sovereign_terms,
                              own_countries):
                    use.company = True
                continue
            left_edge, right_edge = _occurrence_edges(use, scope, contexts)
            for edge, table, terms_table in ((left_edge, end_countries, end_terms),
                                            (right_edge, start_countries,
                                             start_terms)):
                if edge is None:
                    continue
                neighbour = table.get(edge)
                if not neighbour or (neighbour & own_countries):
                    continue
                if any(name in sovereign_terms
                       for name in terms_table.get(edge, ())):
                    continue
                use.company = True
                break


@lru_cache(maxsize=4096)
def _occurrence_variants(needle: str) -> tuple[str, ...]:
    """Project trusted name variants back to positions in the original scope."""
    return tuple(sorted(normalize_address(needle))) if _is_han(needle) else (needle,)


def _name_occurrences(scope: str, needle: str, *, limit=MAX_OCCURRENCES,
                      contexts=None) -> list[_Occurrence]:
    """Locate a name and retain the context needed for a later company review."""
    needle = normalize_key(needle)
    if not needle:
        return []
    spans = set()
    for variant in _occurrence_variants(needle):
        for span in _term_spans(scope, variant):
            spans.add(span)
            if len(spans) > limit:
                raise OccurrenceLimitExceeded('GEOGRAPHIC_OCCURRENCE_LIMIT')
    if not spans:
        return []
    if contexts is None:
        contexts = {}
    if 'fragments' not in contexts:
        fragments = _fragments(scope)
        contexts['fragments'] = (fragments, [offset for _, offset in fragments])
    fragments, offsets = contexts['fragments']
    found = []
    for start, end in sorted(spans):
        first_fragment = bisect_right(offsets, start) - 1
        last_fragment = bisect_right(offsets, end - 1) - 1
        left = offsets[first_fragment]
        right = offsets[last_fragment] + len(fragments[last_fragment][0])
        chunk = scope[left:right]
        if _is_han(needle):
            company = _han_marker_near(chunk, start - left, end - start)
            occurrence = _Occurrence(
                start, end, company, (left, right), None, None, True, needle)
        else:
            key = (left, right)
            if key not in contexts:
                words = [(m.group(), m.start(), m.end()) for m in _WORD.finditer(chunk)]
                eligible = {i: word.casefold() for i, (word, _, word_end) in enumerate(words)
                            if len(word) >= MARKER_MIN_LENGTH and chunk[word_end:word_end + 1] != '-'}
                contexts[key] = (words, [s for _, s, _ in words], [e for _, _, e in words],
                                 eligible, any(w in LATIN_STRONG_MARKERS for w in eligible.values()))
            words, starts, ends, eligible, has_strong = contexts[key]
            first = bisect_right(ends, start - left)
            last = bisect_left(starts, end - left) - 1
            company = _latin_marker_near(
                chunk, words, first, last, eligible, has_strong)
            occurrence = _Occurrence(
                start, end, company, key, first, last, False, needle)
        found.append(occurrence)
    return found


def _outside_longer_names(occurrences, covering_spans):
    """Keep independent mentions, including repetitions beside a nested mention."""
    index = covering_spans if isinstance(covering_spans, _SpanIndex) else _SpanIndex(covering_spans)
    return [occurrence for occurrence in occurrences
            if not index.covers(occurrence.start, occurrence.end)]


def _uncontested(occurrences, iso, local_span_owners):
    """Drop a country word also claimed as a locality in another country."""
    return [occurrence for occurrence in occurrences
            if not any(owner != iso
                       for owner in local_span_owners.get(
                           (occurrence.start, occurrence.end), ()))]


def _effective_support(candidates, scope: str, occurrences, covering_index,
                       local_span_owners):
    """Evidence mass per destination after withdrawing company-name evidence."""
    support: dict[str, float] = {}
    tokens: dict[str, int] = {}
    entity: dict[str, bool] = {}
    strong: dict[str, bool] = {}
    terms: dict[str, set[str]] = {}
    entity_only: dict[str, bool] = {}
    for candidate in candidates:
        suppressed = set()
        for term, _weight in candidate.term_support:
            uses = occurrences[term]
            if term in candidate.entity_terms:
                uses = _outside_longer_names(
                    uses, covering_index(candidate.destination_id))
                uses = _uncontested(
                    uses, candidate.destination_id, local_span_owners)
            if uses and all(occurrence.company for occurrence in uses):
                suppressed.add(term)
            elif not uses and occurrences[term]:
                suppressed.add(term)
        remaining = [(term, weight) for term, weight in candidate.term_support
                     if term not in suppressed]
        support[candidate.destination_id] = sum(weight for _term, weight in remaining)
        tokens[candidate.destination_id] = len(remaining)
        entity[candidate.destination_id] = bool(candidate.entity_terms) and any(
            term not in suppressed for term in candidate.entity_terms)
        strong[candidate.destination_id] = any(
            weight >= STRONG_TERM for _term, weight in remaining)
        terms[candidate.destination_id] = {term for term, _weight in remaining}
        entity_only[candidate.destination_id] = bool(remaining) and all(
            term in candidate.entity_terms for term, _weight in remaining)
    return support, tokens, entity, strong, terms, entity_only


def _resolve_hint(hint: str | None, catalogue: _Catalogue) -> str | None:
    """Map a structured country field to an ISO code, if it is trustworthy."""
    if not hint:
        return None
    value = hint.strip()
    if not value:
        return None
    upper = value.upper()
    if len(upper) == 2 and CODE_RE.fullmatch(upper):
        if upper in catalogue.iso_to_destination:
            return upper
        for destination_id, code in catalogue.destination_codes.items():
            if code == upper:
                return catalogue.destination_iso.get(destination_id)
        return None
    folded = value.casefold()
    for destination_id, aliases in catalogue.names_by_destination.items():
        for alias in aliases:
            if alias and alias.casefold() == folded:
                return catalogue.destination_iso.get(destination_id)
    return None


def classify_record(record: AddressRecord, geo_db: Path, hkp_db: Path,
                    approval: CatalogueApproval | None = None) -> ClassificationResult:
    """Classify offline, with explicit review instead of truncated evidence.

    Address plus hint is limited to 10,000 input characters; the NFKC scope
    also has a 10,000-character limit. More than 1,024 located occurrences returns
    REVIEW_AMBIGUOUS. Original record fields are never changed.
    """
    def result(status, code=None, confidence=0.0, reason='', destination_id=None, evidence=()):
        names = catalogue.names_by_destination.get(destination_id, ('', '', '')) \
            if destination_id else ('', '', '')
        return ClassificationResult(record.record_no, status, code, confidence, reason,
                                    destination_id, evidence=tuple(evidence),
                                    destination_name_en=names[0],
                                    destination_name_tc=names[1])

    if record.input_error:
        return result('INPUT_ERROR', reason=record.input_error)
    if len(record.address_text) + len(record.country_hint or '') > MAX_ADDRESS_CHARS:
        return result('REVIEW_AMBIGUOUS', reason='ADDRESS_TOO_LONG')
    if not record.address_text.strip() and not record.country_hint:
        return result('UNKNOWN', reason='EMPTY_ADDRESS')
    catalogue = _catalogue(Path(hkp_db), approval)
    # The first line of a multi-line address is the recipient, not a place.
    lines = [line.strip() for line in record.address_text.splitlines() if line.strip()]
    scope = '\n'.join(lines[1:]) if len(lines) > 1 else record.address_text
    scope = unicodedata.normalize('NFKC', scope).casefold()
    if len(scope) > MAX_ADDRESS_CHARS:
        return result('REVIEW_AMBIGUOUS', reason='ADDRESS_TOO_LONG')
    if has_unsupported_script(scope):
        return result('UNKNOWN', reason='UNSUPPORTED_LANGUAGE')
    forms = normalize_address(scope)
    try:
        candidates = retrieve_candidates(
            Path(geo_db), forms, record.country_hint,
            retain_unlocatable_terms=True,
        )
    except OccurrenceLimitExceeded:
        return result('REVIEW_AMBIGUOUS', reason='GEOGRAPHIC_OCCURRENCE_LIMIT')
    names = {term for candidate in candidates for term, _ in candidate.term_support}
    names.update(alias for aliases in catalogue.names_by_iso.values() for alias in aliases if alias)
    occurrences = {}
    by_key = {}
    contexts = {}
    remaining = MAX_OCCURRENCES
    try:
        for name in sorted(names):
            key = normalize_key(name)
            variants = _occurrence_variants(key)
            if variants not in by_key:
                by_key[variants] = _name_occurrences(scope, key, limit=remaining, contexts=contexts)
                remaining -= len(by_key[variants])
            occurrences[name] = by_key[variants]
    except OccurrenceLimitExceeded:
        return result('REVIEW_AMBIGUOUS', reason='GEOGRAPHIC_OCCURRENCE_LIMIT')
    if any(not occurrences[term] for candidate in candidates for term, _ in candidate.term_support):
        return result('REVIEW_AMBIGUOUS', reason='UNLOCATABLE_GEOGRAPHIC_TERM')
    (term_countries, entity_countries, sovereign_terms,
     substantial_countries) = _country_maps(candidates)
    (end_countries, start_countries,
     end_terms, start_terms) = _neighbour_index(occurrences, term_countries)
    (substantial_end_countries, substantial_start_countries,
     _settled_end_terms, _settled_start_terms) = _neighbour_index(
         occurrences, substantial_countries)
    _refine_occurrence_context(scope, candidates, occurrences, contexts,
                               substantial_end_countries, substantial_start_countries,
                               entity_countries)
    _mark_brand_country_entities(scope, occurrences, contexts, term_countries,
                                 entity_countries, sovereign_terms,
                                 end_countries, start_countries, end_terms,
                                 start_terms,
                                 [use for uses in occurrences.values()
                                  for use in uses])
    # A longer geographic name owns only its own span. Weight is irrelevant
    # for ordinary localities, but a country entity spelling that resolves to
    # the same country is an alternate official name and does not hide that
    # country's short name.
    country_entity_owners: dict[str, set[str]] = {}
    country_entity_codes: dict[str, set[str]] = {}
    country_entity_weights: dict[str, float] = {}
    terms_by_iso: dict[str, set[str]] = {}
    for candidate in candidates:
        terms_by_iso.setdefault(candidate.destination_id, set()).update(
            term for term, _weight in candidate.term_support)
        for term, feature_code in candidate.entity_feature_codes:
            country_entity_codes.setdefault(term, set()).add(feature_code)
        for term in candidate.entity_terms:
            country_entity_owners.setdefault(term, set()).add(
                candidate.destination_id)
            for name, weight in candidate.term_support:
                if name == term:
                    country_entity_weights[term] = max(
                        country_entity_weights.get(term, 0.0), weight)
    country_entity_terms = set(country_entity_owners)
    dependent_entity_terms = {
        term for term, codes in country_entity_codes.items()
        if codes and "PCLI" not in codes
    }

    local_span_owners = {}
    for candidate in candidates:
        # A same-spelled village in another country is common in a global
        # gazetteer ("India" exists as a tiny settlement). It should withdraw a
        # country name only when that local reading has corroboration from a
        # separate, non-company term that the country reading does not also
        # use. The population of the same-spelled place is not independent
        # evidence.
        if candidate.support < MIN_SUPPORT:
            continue
        independent_terms = {
            term for term, _weight in candidate.term_support
            if any(not occurrence.company for occurrence in occurrences[term])
        }
        for term, weight in candidate.term_support:
            if term in candidate.entity_terms or not (independent_terms - {term}):
                continue
            if weight < MIN_SUPPORT:
                continue
            # A village that merely shares a country name may only displace
            # that country when its own destination is at least as strong as
            # the country entity. Otherwise the country reading stands and
            # the rival becomes an explicit review instead of a silent
            # match on the wrong country.
            if candidate.support < country_entity_weights.get(term, 0.0):
                continue
            # The local place itself must be substantial. Two tiny same-spelled
            # villages must not erase a country.
            country_owners = country_entity_owners.get(term, set())
            blocked_terms = {
                other_term
                for owner in country_owners
                for other_term in terms_by_iso.get(owner, ())
            }
            other_terms = independent_terms - {term}
            plain_terms = other_terms - country_entity_terms
            # An explicit parent country is valid context for a genuine
            # locality ("Macau, Brazil"), but not for a sovereign country
            # namesake ("China, United States" / "Italy, Brazil").
            parent_terms = {
                other for other in other_terms & country_entity_terms
                if (term in dependent_entity_terms
                    and candidate.destination_id in country_entity_owners.get(other, ()))
            }
            if not ((plain_terms | parent_terms) - blocked_terms):
                continue
            for occurrence in occurrences[term]:
                if occurrence.company:
                    continue
                local_span_owners.setdefault(
                    (occurrence.start, occurrence.end), set()).add(
                        candidate.destination_id)

    covering_cache: dict[str, _SpanIndex] = {}

    def covering_index(iso: str) -> _SpanIndex:
        cached = covering_cache.get(iso)
        if cached is not None:
            return cached
        aliases = catalogue.names_by_iso.get(iso, ())
        sovereign_terms = {
            term for candidate in candidates
            for term, _weight in candidate.term_support
            if any(_is_sovereign_country_expansion(term, alias)
                   for alias in aliases if alias)
        }
        spans = {(occurrence.start, occurrence.end)
                 for candidate in candidates
                 for term, _weight in candidate.term_support
                 if not (candidate.destination_id == iso
                         and term in candidate.entity_terms)
                 and term not in sovereign_terms
                 for occurrence in occurrences[term]}
        spans.update((occurrence.start, occurrence.end)
                     for other_iso, aliases in catalogue.names_by_iso.items()
                     if other_iso != iso
                     for alias in aliases
                     if alias
                     for occurrence in occurrences[alias])
        cached = _SpanIndex(spans)
        covering_cache[iso] = cached
        return cached

    support, tokens, entity, strong, terms, entity_only = _effective_support(
        candidates, scope, occurrences, covering_index, local_span_owners)

    assertion_alias: dict[str, str] = {}
    withdrawn_alias: dict[str, str] = {}
    # A country name that appears only inside a company or street name is
    # withdrawn from the evidence, but it still contradicts a different
    # destination rather than silently agreeing with one.
    for iso, aliases in catalogue.names_by_iso.items():
        # A full country entity can extend a catalogue name without changing
        # its identity. Its own occurrence supplies the company context too.
        expanded = [term for candidate in candidates if candidate.destination_id == iso
                    for term in candidate.entity_terms
                    if any(alias and contains_keyed(term, alias) for alias in aliases)]
        for alias in (*aliases, *expanded):
            if not alias:
                continue
            uses = _outside_longer_names(occurrences[alias], covering_index(iso))
            uses = _uncontested(uses, iso, local_span_owners)
            if any(not occurrence.company for occurrence in uses):
                assertion_alias[iso] = alias
            elif uses:
                withdrawn_alias[iso] = alias
    withdrawn_alias = {iso: alias for iso, alias in withdrawn_alias.items()
                       if iso not in assertion_alias}
    assertions = {iso: 'CATALOGUE_NAME' for iso in assertion_alias}
    withdrawn_names = dict(withdrawn_alias)
    hint_iso = _resolve_hint(record.country_hint, catalogue)
    if hint_iso:
        assertions.setdefault(hint_iso, 'STRUCTURED_HINT')

    def viable(iso: str) -> bool:
        return (support.get(iso, 0.0) >= MIN_SUPPORT
                and strong.get(iso, False)
                and (tokens.get(iso, 0) >= 2 or entity.get(iso, False)))

    def independent(iso: str, leader: str) -> bool:
        """A rival must contribute evidence the leader does not also have.

        A rival whose remaining terms all sit inside a longer term of the
        leader is a less specific reading of the very same words, so it is
        not a rival at all.
        """
        leader_terms = terms.get(leader, set())
        own = terms.get(iso, set()) - leader_terms
        if not own:
            return False
        leader_spans = {
            (occurrence.start, occurrence.end)
            for term in leader_terms
            for occurrence in occurrences[term]
            if not occurrence.company
        }
        return any(_outside_longer_names(
            [occurrence for occurrence in occurrences[term]
             if not occurrence.company],
            leader_spans) or not occurrences[term] for term in own)

    def matched(iso: str):
        destination_id = catalogue.iso_to_destination.get(iso)
        code = catalogue.destination_codes.get(destination_id) if destination_id else None
        if not code:
            # The geography was resolved, but the catalogue issues no code
            # for it. The resolved country is kept in the evidence, so the
            # reviewer sees *which* destination is missing instead of an
            # anonymous review.
            return result('REVIEW_CODE_MAPPING',
                          reason='GEOGRAPHY_HAS_NO_APPROVED_HKP_MAPPING',
                          evidence=(f'GEOGRAPHY:{iso}',))
        evidence = support.get(iso, 0.0)
        if evidence >= MIN_SUPPORT:
            return result('MATCHED', code, min(0.99, evidence), 'GEOGRAPHIC_EVIDENCE',
                          destination_id, evidence=sorted(terms.get(iso, set())))
        return result('MATCHED', code, 0.98, 'EXPLICIT_DESTINATION', destination_id,
                      evidence=sorted(terms.get(iso, set())))

    if len(assertions) > 1:
        return result('REVIEW_CONFLICT', reason='CONTRADICTORY_EXPLICIT_DESTINATIONS')

    if assertions:
        target = next(iter(assertions))
        for iso in withdrawn_names:
            if iso != target:
                return result('REVIEW_CONFLICT',
                              reason='WITHDRAWN_COUNTRY_NAME_CONFLICTS_WITH_DESTINATION')
        evidence = support.get(target, 0.0)
        if evidence >= MIN_SUPPORT:
            rivals = [iso for iso in support
                      if iso != target and support[iso] >= RIVAL_RATIO * evidence
                      and viable(iso) and independent(iso, target)
                      and not (assertions[target] == 'CATALOGUE_NAME'
                               and entity_only.get(iso, False))]
            if rivals:
                return result('REVIEW_AMBIGUOUS', reason='MULTIPLE_STRONG_GEOGRAPHIC_DESTINATIONS')
            return matched(target)
        contradicting = [iso for iso, value in support.items()
                         if iso != target and value >= MIN_SUPPORT]
        if contradicting:
            return result('REVIEW_CONFLICT', reason='EXPLICIT_DESTINATION_CONFLICTS_WITH_GEOGRAPHY')
        return matched(target)

    options = sorted((iso for iso in support if viable(iso)), key=lambda iso: (-support[iso], iso))
    if not options:
        # No destination carries enough evidence to be asserted. Several
        # comparable destinations still mean "review this", while a single
        # one only means "not enough evidence".
        contenders = sorted((iso for iso, value in support.items() if value >= MIN_SUPPORT),
                            key=lambda iso: (-support[iso], iso))
        if len(contenders) > 1:
            leader = contenders[0]
            rivals = [iso for iso in contenders[1:]
                      if support[iso] >= RIVAL_RATIO * support[leader]]
            if rivals:
                return result('REVIEW_AMBIGUOUS', reason='MULTIPLE_PLAUSIBLE_GEOGRAPHIC_DESTINATIONS')
        if contenders:
            return result('UNKNOWN', reason='SINGLE_PLACE_IS_NOT_ENOUGH')
        return result('UNKNOWN', reason='NO_GEOGRAPHIC_MATCH')
    leader = options[0]
    rivals = [iso for iso in options[1:]
              if support[iso] >= RIVAL_RATIO * support[leader] and independent(iso, leader)]
    if rivals:
        return result('REVIEW_AMBIGUOUS', reason='MULTIPLE_PLAUSIBLE_GEOGRAPHIC_DESTINATIONS')
    return matched(leader)
