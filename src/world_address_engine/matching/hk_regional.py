"""Bounded, read-only ALS address evidence; never validates deliverability.

Callers supply eligible address-role text (country.py owns recipient/company
filtering). Official translations are alternative spellings of a component,
not independent votes. Components are joined only on an address ID.
"""
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import unicodedata

from world_address_engine.data.hk_regional import normalize_hk_key, verify_hk_pack

_MAX_CANDIDATES = 64
_MAX_ALIASES = 4096
_HAN = r'\u3400-\u9fff'
_NUMBER = r'(?:[0-9]+[a-z]?|[零〇一二兩两三四五六七八九十百千]+)'
_DIGITS = dict(zip('零〇一二兩两三四五六七八九', (0, 0, 1, 2, 2, 2, 3, 4, 5, 6, 7, 8, 9)))
_COMPONENT_SUFFIX = re.compile(
    r'^\s*(?:(?:road|rd|street|st|avenue|ave|lane|ln|drive|dr|building|bldg|'
    r'tower|house|estate|centre|center|plaza)\b|[街路巷弄邨苑]|大廈|大厦|大樓|大楼|中心|廣場|广场)')
_RECIPIENT_ROLE = re.compile(
    r'^\s*(?:attn|attention|to|mr|mrs|ms|miss|dr|prof)(?:\b[\s.:：]+)|^\s*(?:收件人|聯絡人|联系人)', re.I)
_COMPANY_ROLE = re.compile(
    r'\b(?:ltd|limited|inc|llc|corp|corporation|company|co|gmbh|bank|holdings|trading|logistics)\b'
    r'|有限公司|公司|集團|集团|銀行|银行', re.I)
_UNIT_PREFIX = re.compile(
    r'\b(?:flat|room|floor|unit|suite|level|block|tower)\s*(?:no\s*)?$|[樓楼室座]\s*$', re.I)


def eligible_hk_lines(text):
    """Filter recipient/company roles before general country eligibility.

    Keep punctuation between retained address fragments so their context is
    available until key normalization. Never rescue an address-looking company
    fragment merely because it begins with a number.
    """
    lines = []
    for raw in text.splitlines():
        line = unicodedata.normalize('NFKC', raw).casefold().strip()
        if not line or _RECIPIENT_ROLE.search(line):
            continue
        parts = [part.strip() for part in re.split(r'[,;，；]', line)]
        kept = [part for part in parts if part and not _COMPANY_ROLE.search(part)]
        if kept:
            lines.append(', '.join(kept))
    return tuple(lines)


@dataclass(frozen=True, slots=True)
class HKRegionalMatch:
    address_ids: tuple[str, ...]
    evidence: tuple[str, ...]


def _anchors(text):
    values = set(re.findall(r'[a-z][a-z0-9]*', text))
    for run in re.findall('[' + _HAN + ']{2,}', text):
        values.update(run[i:i + size] for size in (2, 3)
                      for i in range(len(run) - size + 1))
    return sorted(values)


def _alias_pattern(key):
    # Han may directly adjoin other Han components or a house number. Latin
    # aliases must not match within longer street/building/company words.
    # Unicode Latin words have boundaries too; Han components may adjoin an
    # English translation without punctuation in mixed-script address lines.
    word = r'[^\W_' + _HAN + ']'
    left = r'(?<!' + word + ')' if key[0].isascii() and key[0].isalnum() else ''
    right = r'(?!' + word + ')' if key[-1].isascii() and key[-1].isalnum() else ''
    return left + re.escape(key) + right


def _number(value):
    value = value.strip().casefold()
    if len(value) > 16:
        return -1, ''
    match = re.fullmatch(r'(\d+)([a-z]?)', value)
    if match:
        return int(match[1]), match[2]
    if not value or any(char not in _DIGITS and char not in '十百千' for char in value):
        return None
    total = digit = 0
    for char in value:
        if char in _DIGITS:
            digit = digit * 10 + _DIGITS[char]
        else:
            total += (digit or 1) * {'十': 10, '百': 100, '千': 1000}[char]
            digit = 0
    return total + digit, ''


def _street_numbers(line, match):
    before, after = line[:match.start()], line[match.end():]
    numbers = []
    # Arabic house numbers precede English street names; Chinese addresses
    # normally follow the street and explicitly mark 號/号. Keep floor/unit
    # digits elsewhere in the address out of the house-number evidence.
    range_pattern = '(' + _NUMBER + r')(?:\s*(?:至|to)\s*(' + _NUMBER + '))?'
    leading = re.search(r'(?<![a-z0-9])' + range_pattern + r'\s*$', before)
    if leading and not _UNIT_PREFIX.search(before[:leading.start()]):
        numbers.extend(_number(value) for value in leading.groups() if value)
        if leading[2] and numbers[-1] < numbers[-2]:
            return ((-1, ''),)
    trailing = re.match(r'\s*(?:no\s*|number\s*|第\s*)?' + range_pattern + r'(?=[號号]|\s|$)', after)
    if trailing:
        remainder = after[trailing.end():].strip()
        if not re.match(r'(?:f|fl|floor|flat|room|unit)\b|[樓楼室]', remainder):
            values = [_number(value) for value in trailing.groups() if value]
            if len(values) == 2 and values[1] < values[0]:
                return ((-1, ''),)
            numbers.extend(values)
    return tuple(number for number in numbers if number is not None)


def _number_agrees(number, low, high):
    start, end = _number(low or ''), _number(high or low or '')
    if start is None or end is None or start[0] < 0 or end[0] < 0 or end < start:
        return False
    return start <= number <= end


class HKRegionalMatcher:
    """A selected, verified regional pack; close explicitly or use ``with``."""

    def __init__(self, db_path):
        self.path = Path(db_path).resolve()
        verify_hk_pack(self.path)
        self._db = sqlite3.connect(self.path.as_uri() + '?mode=ro&immutable=1', uri=True)
        self._db.execute('PRAGMA query_only=ON')

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None

    def match(self, text):
        if self._db is None:
            raise RuntimeError('Hong Kong regional matcher is closed')
        if len(text) > 10_000:
            return None
        # Retain explicit range structure before punctuation folding; otherwise
        # 99-12 would be mistaken for house 12 and hide a contradiction.
        lines = tuple(normalize_hk_key(re.sub(
            r'(\d+[a-zA-Z]?)\s*[-–—~]\s*(\d+[a-zA-Z]?)', r'\1至\2',
            unicodedata.normalize('NFKC', line)))
            for line in eligible_hk_lines(text))
        candidates = set()
        for anchor in _anchors(' '.join(lines)):
            # The anchor/address composite index covers DISTINCT and LIMIT.
            rows = self._db.execute(
                'SELECT DISTINCT address_id FROM hk_aliases INDEXED BY hk_alias_anchor '
                'WHERE anchor=? LIMIT ?', (anchor, _MAX_CANDIDATES + 1)).fetchall()
            if len(rows) > _MAX_CANDIDATES:
                continue
            candidates.update(row[0] for row in rows)
            if len(candidates) > _MAX_CANDIDATES:
                return None
        accepted, evidence = [], set()
        for address_id in sorted(candidates):
            row = self._db.execute(
                'SELECT number_from,number_to,number_conflict FROM hk_addresses '
                'WHERE address_id=?', (address_id,)).fetchone()
            if row is None:
                continue
            aliases = self._db.execute(
                'SELECT kind,search_key FROM hk_aliases INDEXED BY hk_alias_address '
                'WHERE address_id=? LIMIT ?', (address_id, _MAX_ALIASES + 1)).fetchall()
            if len(aliases) > _MAX_ALIASES:
                continue
            roles, groups, numbers = {}, {}, []
            for kind, key in aliases:
                if key:
                    groups.setdefault(kind, set()).add(key)
            for kind, key in aliases:
                if not key:
                    continue
                for index, line in enumerate(lines):
                    for match in re.finditer(_alias_pattern(key), line):
                        if _COMPONENT_SUFFIX.match(line[match.end():]):
                            continue
                        roles.setdefault(kind, set()).add((index, *match.span()))
                        if kind == 'street':
                            numbers.extend(_street_numbers(line, match))
            low, high, conflict = row
            if numbers and (conflict or any(not _number_agrees(n, low, high) for n in numbers)):
                continue
            def independent(kind):
                # Compare whole bilingual/derived alias groups, not selected
                # spellings. Two translations of one component are one signal.
                if groups.get(kind, set()) & groups.get('street', set()):
                    return False
                return any(a[0] != b[0] or a[1] >= b[2] or b[1] >= a[2]
                           for a in roles.get(kind, ()) for b in roles.get('street', ()))

            building_street = independent('building') or independent('estate')
            numbered_street = bool(numbers) and not conflict and independent('district')
            if building_street or numbered_street:
                accepted.append(address_id)
                evidence.update(('street', 'building_or_estate') if building_street
                                else ('street', 'house_number', 'district'))
        if not accepted:
            return None
        return HKRegionalMatch(tuple(accepted), tuple(sorted(evidence)))
