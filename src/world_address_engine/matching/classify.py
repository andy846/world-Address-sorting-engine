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
from dataclasses import dataclass, field
from pathlib import Path

from world_address_engine.hkp.approval import CatalogueApproval
from world_address_engine.models import AddressRecord, ClassificationResult
from world_address_engine.matching.normalize import (
    contains_keyed, has_unsupported_script, normalize_address, normalize_key,
)
from world_address_engine.matching.retrieve import MIN_SUPPORT, retrieve_candidates
from world_address_engine.sqlite_util import open_db

CODE_RE = re.compile(r"[A-Z]{2}")

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


def _fragment_words(text: str) -> list[tuple[str, int, list[tuple[str, int, int]]]]:
    result = []
    for chunk, offset in _fragments(text):
        words = [(m.group(0), offset + m.start(), offset + m.end()) for m in _WORD.finditer(chunk)]
        result.append((chunk, offset, words))
    return result


def _latin_pattern(tokens: list[str]) -> re.Pattern[str]:
    body = r"[\s\-_.'\u2019\u2018]*".join(re.escape(token) for token in tokens)
    edge = r"[0-9A-Za-z\u00c0-\u024f\u1e00-\u1eff]"
    return re.compile(r"(?<!" + edge + r")" + body + r"(?!" + edge + r")", re.IGNORECASE)


def _latin_occurrences(scope: str, tokens: list[str]):
    pattern = _latin_pattern(tokens)
    for chunk, offset, words in _fragment_words(scope):
        for match in pattern.finditer(chunk):
            start = offset + match.start()
            end = offset + match.end()
            covered = [i for i, (_w, s, e) in enumerate(words) if s < end and e > start]
            if covered:
                yield chunk, words, covered[0], covered[-1]


def _han_occurrences(scope: str, needle: str):
    for chunk, _offset, _words in _fragment_words(scope):
        index = chunk.find(needle)
        while index >= 0:
            yield chunk, index
            index = chunk.find(needle, index + 1)


def _latin_marker_near(chunk: str, words, first: int, last: int) -> bool:
    """True when a legal-form marker sits beside the matched phrase."""
    eligible: dict[int, str] = {}
    for index, (word, _start, end) in enumerate(words):
        token = word.casefold()
        if len(token) < MARKER_MIN_LENGTH:
            continue
        # A marker glued to a hyphenated compound belongs to a proper noun.
        if chunk[end:end + 1] == '-':
            continue
        eligible[index] = token
    low = max(0, first - MARKER_WINDOW)
    high = min(len(words) - 1, last + MARKER_WINDOW)
    nearby = [eligible[i] for i in range(low, high + 1) if i in eligible]
    if any(token in LATIN_STRONG_MARKERS for token in nearby):
        return True
    if any(token in LATIN_WEAK_MARKERS for token in nearby):
        return any(token in LATIN_STRONG_MARKERS for token in eligible.values())
    return False


def _latin_trailing_word(words, last: int) -> bool:
    """True when the matched phrase is followed by another word in its fragment.

    A country name followed by another word belongs to an organisation or a
    street rather than to the address structure: "China Telecom", "London
    Road", "Hong Kong Airlines". A following number or postal code does not
    make it a company name.
    """
    if last + 1 >= len(words):
        return False
    following = words[last + 1][0]
    if not following[:1].isalpha():
        return False
    return following.casefold() not in TRAILING_EXEMPT


def _han_marker_near(chunk: str, index: int, length: int) -> bool:
    before = chunk[max(0, index - MARKER_CHARS):index]
    after = chunk[index + length:index + length + MARKER_CHARS]
    if any(marker in before or marker in after for marker in HAN_STRONG_MARKERS):
        return True
    if any(marker in before or marker in after for marker in HAN_WEAK_MARKERS):
        return any(marker in chunk for marker in HAN_STRONG_MARKERS)
    return False


def _is_company_adjacent(scope: str, needle: str) -> bool:
    """True when every occurrence of `needle` belongs to a company name."""
    if not needle:
        return False
    if _is_han(needle):
        occurrences = list(_han_occurrences(scope, needle))
        if not occurrences:
            return False
        return all(_han_marker_near(chunk, index, len(needle)) for chunk, index in occurrences)
    tokens = needle.split()
    if not tokens:
        return False
    occurrences = list(_latin_occurrences(scope, tokens))
    if not occurrences:
        return False
    return all(_latin_marker_near(chunk, words, first, last)
               or _latin_trailing_word(words, last)
               for chunk, words, first, last in occurrences)


def _effective_support(candidates, scope: str):
    """Evidence mass per destination after withdrawing company-name evidence."""
    support: dict[str, float] = {}
    tokens: dict[str, int] = {}
    entity: dict[str, bool] = {}
    strong: dict[str, bool] = {}
    terms: dict[str, set[str]] = {}
    entity_only: dict[str, bool] = {}
    for candidate in candidates:
        suppressed = {term for term, _weight in candidate.term_support
                      if _is_company_adjacent(scope, term)}
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
    """Classify one record against the reference pack and the HKP master."""
    def result(status, code=None, confidence=0.0, reason='', destination_id=None):
        return ClassificationResult(record.record_no, status, code, confidence, reason, destination_id)

    if record.input_error:
        return result('INPUT_ERROR', reason=record.input_error)
    if not record.address_text.strip() and not record.country_hint:
        return result('UNKNOWN', reason='EMPTY_ADDRESS')
    if has_unsupported_script(record.address_text):
        return result('UNKNOWN', reason='UNSUPPORTED_LANGUAGE')

    catalogue = _catalogue(Path(hkp_db), approval)
    # The first line of a multi-line address is the recipient, not a place.
    lines = [line.strip() for line in record.address_text.splitlines() if line.strip()]
    scope = '\n'.join(lines[1:]) if len(lines) > 1 else record.address_text

    candidates = retrieve_candidates(Path(geo_db), normalize_address(scope), record.country_hint)
    support, tokens, entity, strong, terms, entity_only = _effective_support(candidates, scope)

    assertions: dict[str, str] = {}
    # A country name that appears only inside a company or street name is
    # withdrawn from the evidence, but it still contradicts a different
    # destination rather than silently agreeing with one.
    withdrawn_names: dict[str, str] = {}
    scope_key = normalize_key(scope)
    for iso, aliases in catalogue.names_by_iso.items():
        for alias in aliases:
            if alias and contains_keyed(scope_key, alias):
                if _is_company_adjacent(scope, alias):
                    withdrawn_names.setdefault(iso, 'CATALOGUE_NAME_WITHDRAWN')
                else:
                    assertions[iso] = 'CATALOGUE_NAME'
                break
    hint_iso = _resolve_hint(record.country_hint, catalogue)
    if hint_iso:
        assertions.setdefault(hint_iso, 'STRUCTURED_HINT')

    def viable(iso: str) -> bool:
        return (support.get(iso, 0.0) >= MIN_SUPPORT
                and strong.get(iso, False)
                and (tokens.get(iso, 0) >= 2 or entity.get(iso, False)))

    def independent(iso: str, leader: str) -> bool:
        """A rival must contribute evidence the leader does not also have."""
        return bool(terms.get(iso, set()) - terms.get(leader, set()))

    def matched(iso: str):
        destination_id = catalogue.iso_to_destination.get(iso)
        code = catalogue.destination_codes.get(destination_id) if destination_id else None
        if not code:
            return result('REVIEW_CODE_MAPPING', reason='GEOGRAPHY_HAS_NO_APPROVED_HKP_MAPPING')
        evidence = support.get(iso, 0.0)
        if evidence >= MIN_SUPPORT:
            return result('MATCHED', code, min(0.99, evidence), 'GEOGRAPHIC_EVIDENCE', destination_id)
        return result('MATCHED', code, 0.98, 'EXPLICIT_DESTINATION', destination_id)

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
