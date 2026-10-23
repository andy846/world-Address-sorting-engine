"""Offline country-code estimates for list statistics, not postal approval."""
from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from pathlib import Path
import re
import sqlite3
import unicodedata

from world_address_engine.matching.normalize import normalize_address, normalize_key
from world_address_engine.matching.retrieve import retrieve_candidates, OccurrenceLimitExceeded
from world_address_engine.models import AddressRecord

COUNTRY_RULES_VERSION = '2026-10-23.country.1'
RIVAL_RATIO = 0.55
MAX_ADDRESS_CHARS = 10_000


@dataclass(frozen=True, slots=True)
class CountryInference:
    record_no: int
    country_code: str | None
    status: str
    reason: str
    evidence: tuple[str, ...] = ()
    candidates: tuple[str, ...] = ()

    def __post_init__(self):
        if self.record_no < 1 or self.status not in {'DETERMINED', 'INFERRED', 'UNRESOLVED'}:
            raise ValueError('invalid country inference')
        if (self.status == 'UNRESOLVED') != (self.country_code is None):
            raise ValueError('country inference status and code disagree')
        if self.country_code is not None and not re.fullmatch('[A-Z]{2}', self.country_code):
            raise ValueError('invalid geographic country code')


# These are geographic spellings, not a conversion of arbitrary ISO tokens.
COUNTRY_ALIASES = {
    'HK': ('Hongkong', 'Hong Kong SAR', '香港特别行政区', '香港特別行政區',
           '中华人民共和国香港特别行政区', '中華人民共和國香港特別行政區'),
    'CN': ('China', 'Mainland China', '中国', '中國', '中华人民共和国',
           '中華人民共和國', 'PR China', 'P.R. China', "People's Republic of China"),
    'GB': ('United Kingdom', 'Great Britain', 'Britain', 'England', 'Scotland',
           'Wales', 'Northern Ireland'),
    'US': ('United States', 'United States of America', 'USA', 'U.S.A.'),
    'MO': ('Macao', 'Macau', '澳门', '澳門', '澳门特别行政区', '澳門特別行政區'),
    'TW': ('Taiwan', '台灣', '臺灣', '台湾', 'Republic of China'),
    'KR': ('South Korea', 'Korea South'), 'KP': ('North Korea', 'Korea North'),
    'TP': ('Timor Leste', 'East Timor'), 'VN': ('Vietnam',),
}
SHORT_TAIL_CODES = {'hk': 'HK', 'h k': 'HK', 'kln': 'HK', 'uk': 'GB',
                    'u k': 'GB', 'us': 'US', 'u s': 'US', 'prc': 'CN',
                    'p r c': 'CN'}
HK_AREAS = (
    'kowloon', 'new territories', 'tuen mun', 'yuen long', 'sha tin', 'shatin',
    'tsuen wan', 'kwai chung', 'kwai tsing', 'sai kung', 'tai po', 'taipo',
    'fanling', 'fan ling', 'sheung shui', 'tseung kwan o', 'ma on shan',
    'tin shui wai', 'lantau', 'cheung chau', 'peng chau', 'tung chung',
    'tai wai', 'fo tan', 'tsing yi', 'lam tin', 'kwun tong', 'wong tai sin',
    'kowloon bay', 'san po kong', 'mong kok', 'mongkok', 'yau ma tei',
    'tsim sha tsui', 'sham shui po', 'lai chi kok', 'cheung sha wan',
    'hung hom', 'ho man tin', 'to kwa wan', 'tai kok tsui', 'yau tong',
    'causeway bay', 'wan chai', 'wanchai', 'north point', 'quarry bay',
    'chai wan', 'sai wan ho', 'shau kei wan', 'kennedy town', 'pok fu lam',
    'repulse bay', 'ap lei chau', 'sai ying pun', 'happy valley',
    'chuk yuen', 'lok fu', 'diamond hill', 'sham tseng', 'discovery bay',
    '九龍', '九龙', '新界', '屯門', '屯门', '元朗', '沙田', '荃灣', '荃湾',
    '葵涌', '葵青', '西貢', '西贡', '大埔', '粉嶺', '粉岭', '上水', '將軍澳',
    '将军澳', '馬鞍山', '马鞍山', '天水圍', '天水围', '大嶼山', '大屿山',
    '長洲', '长洲', '坪洲', '東涌', '东涌', '大圍', '大围', '火炭', '青衣',
    '藍田', '蓝田', '觀塘', '观塘', '黃大仙', '黄大仙', '九龍灣', '九龙湾',
    '新蒲崗', '新蒲岗', '旺角', '油麻地', '尖沙咀', '深水埗', '荔枝角',
    '長沙灣', '长沙湾', '紅磡', '红磡', '何文田', '土瓜灣', '土瓜湾', '大角咀',
    '油塘', '銅鑼灣', '铜锣湾', '灣仔', '湾仔', '北角', '鰂魚涌', '鲗鱼涌',
    '柴灣', '柴湾', '西灣河', '西湾河', '筲箕灣', '筲箕湾', '堅尼地城',
    '坚尼地城', '薄扶林', '鴨脷洲', '鸭脷洲', '西營盤', '西营盘', '跑馬地',
    '跑马地', '竹園', '竹园', '樂富', '乐富', '鑽石山', '钻石山',
    '深井', '愉景灣', '愉景湾', '中環', '中环', '半山',
    'sheung wan', 'ngau tau kok', 'ngau chi wan', 'shek kip mei',
    'shek tong tsui', 'wong chuk hang', 'siu sai wan', 'sau mau ping',
    'kam tin', 'pat heung', 'lau fau shan', 'sha tau kok', 'taikoo',
    'tai koo', 'tai hang', 'san tin', 'lok ma chau', 'sai ying pun',
    '上環', '上环', '牛頭角', '牛头角', '牛池灣', '牛池湾', '石硤尾',
    '石塘咀', '黃竹坑', '黄竹坑', '小西灣', '小西湾', '秀茂坪', '錦田',
    '锦田', '八鄉', '八乡', '流浮山', '沙頭角', '沙头角', '太古',
    '大坑', '新田', '落馬洲', '落马洲',
)
HK_AREAS = tuple(dict.fromkeys((*HK_AREAS, *(name.replace(' ', '')
                            for name in HK_AREAS if ' ' in name))))
CN_REGIONS = (
    '北京', '上海', '天津', '重慶', '重庆', '廣東', '广东', '廣西', '广西',
    '福建', '浙江', '江蘇', '江苏', '山東', '山东', '河北', '河南', '湖北',
    '湖南', '安徽', '江西', '海南', '四川', '貴州', '贵州', '雲南', '云南',
    '陝西', '陕西', '山西', '遼寧', '辽宁', '吉林', '黑龍江', '黑龙江',
    '甘肅', '甘肃', '青海', '寧夏', '宁夏', '新疆', '西藏', '內蒙古', '内蒙古',
    'beijing', 'shanghai', 'tianjin', 'chongqing', 'guangdong', 'guangxi',
    'fujian', 'zhejiang', 'jiangsu', 'shandong', 'hebei', 'henan', 'hubei',
    'hunan', 'anhui', 'jiangxi', 'hainan', 'sichuan', 'guizhou', 'yunnan',
    'shaanxi', 'shanxi', 'liaoning', 'jilin', 'heilongjiang', 'gansu',
    'qinghai', 'ningxia', 'xinjiang', 'tibet', 'inner mongolia',
)
_COMPANY = re.compile(
    r'\b(?:ltd|limited|inc|llc|corp|corporation|company|bank|holdings|trading|logistics)\b'
    r'|有限公司|公司|集團|集团|銀行|银行|china\s+(?:mobile|eastern|southern)', re.I)
_ADDRESS = re.compile(r'\d|\b(?:road|street|avenue|lane|flat|floor|block|room)\b|[路街巷弄號号樓楼]', re.I)
_RECIPIENT = re.compile(r'^(?:mr|mrs|ms|miss|dr|prof|attn|attention)\.?\s|^(?:收件人|聯絡人|联系人)', re.I)
_STREET_AFTER = re.compile(r'^\s*(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b|^[街路巷弄]', re.I)
_STREET_ADDRESS = re.compile(
    r'^\s*\d+[a-z]?\s+.+\b(?:street|st|road|rd|avenue|ave|lane|ln|drive|dr|boulevard|blvd)\b', re.I)


def _location_lines(lines):
    result = []
    for index, line in enumerate(lines):
        if _RECIPIENT.search(line):
            continue
        fragments = [part.strip() for part in re.split(r'[,;，；]', line)]
        kept = [part for part in fragments if part and (
            not _COMPANY.search(part) or _STREET_ADDRESS.search(part))]
        if kept:
            result.append((index, ', '.join(kept)))
    return result


def _regional_match(scope, names):
    for name in names:
        for match in re.finditer(_pattern(name), scope):
            if not _STREET_AFTER.match(scope[match.end():]):
                return True
    return False


def _pattern(name):
    name = normalize_key(name)
    if re.search('[a-z]', name):
        return r'(?<![a-z0-9])' + r'[\s.,_-]+'.join(map(re.escape, name.split())) + r'(?![a-z0-9])'
    return re.escape(name)


def _contains(text, name):
    return re.search(_pattern(name), text) is not None


_WHOLE_REGION = re.compile('(?:' + '|'.join(_pattern(name) for name in (*CN_REGIONS, *HK_AREAS))
                           + r')(?:\s+province|省|市|自治區|自治区)?')


class CountryClassifier:
    """Reusable, bounded estimator; catalogue codes have their own namespace."""
    rules_version = COUNTRY_RULES_VERSION

    def __init__(self, geo_db: Path, catalogue=None):
        if catalogue is None:
            from world_address_engine.data.country_codes import load_country_codes
            catalogue = load_country_codes()
        self.geo_db = Path(geo_db)
        if not self.geo_db.is_file():
            raise FileNotFoundError(self.geo_db)
        self.catalogue = catalogue
        self._cache = OrderedDict()
        self._db = None
        self._names = []
        for code, entry in catalogue.entries.items():
            aliases = (entry.name_en, entry.name_tc, *entry.aliases, *COUNTRY_ALIASES.get(code, ()))
            seen = set()
            for name in aliases:
                for variant in normalize_address(name):
                    if len(variant) >= 2 and variant not in seen:
                        self._names.append((code, variant, re.compile(_pattern(variant))))
                        seen.add(variant)
        self._names.sort(key=lambda item: -len(item[1]))
        self._whole_aliases = frozenset(alias for _code, alias, _pattern in self._names)

    def _eligible_lines(self, lines):
        locations = _location_lines(lines)
        if len(lines) == 1:
            return locations
        start = next((i for i, line in locations if _ADDRESS.search(line)), len(lines))
        result = []
        for i, line in locations:
            plain = line.strip(' ,.;:/()-')
            whole_region = _WHOLE_REGION.fullmatch(plain)
            # A leading name block can contain untitled recipients after a
            # company header. Only whole geographic headings survive it.
            if i < start and plain not in self._whole_aliases and not whole_region:
                short = re.sub(r'[\s.,-]+', ' ', plain).strip()
                if short not in SHORT_TAIL_CODES:
                    latin_name = bool(re.fullmatch(r'[a-z]+(?:\s+[a-z]+){1,2}', plain))
                    ends_in_country = any(plain.endswith(' ' + alias)
                                          for alias in self._whole_aliases)
                    if i == 0 or (latin_name and ends_in_country):
                        continue
            result.append((i, line))
        return result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        if self._db is not None:
            self._db.close()
            self._db = None
        self._cache.clear()

    def classify(self, record: AddressRecord) -> CountryInference:
        if record.input_error:
            return CountryInference(record.record_no, None, 'UNRESOLVED', record.input_error)
        if len(record.address_text) + len(record.country_hint or '') > MAX_ADDRESS_CHARS:
            return CountryInference(record.record_no, None, 'UNRESOLVED', 'ADDRESS_TOO_LONG')
        key = (record.address_text, record.country_hint)
        value = self._cache.get(key)
        if value is None:
            value = self._infer(*key)
            self._cache[key] = value
            if len(self._cache) > 8192:
                self._cache.popitem(last=False)
        else:
            self._cache.move_to_end(key)
        return CountryInference(record.record_no, *value)

    def _explicit(self, lines):
        found = set()
        eligible = {i for i, _line in self._eligible_lines(lines)}
        for index, line in _location_lines(lines):
            territory = re.search(
                r'(?<![a-z])(hong[\s-]*kong|macau|macao|香港|澳門|澳门)(?:\s+sar)?'
                r'[\s,]*(?:china|中国|中國)\s*$', line)
            if territory:
                key = re.sub(r'[\s-]', '', territory[1])
                found.add('HK' if key in {'hongkong', '香港'} else 'MO')
                continue
            if index not in eligible:
                continue
            short = re.sub(r'[\s.,-]+', ' ', line).strip()
            code = SHORT_TAIL_CODES.get(short)
            if code in self.catalogue.entries and index >= max(0, len(lines) - 2):
                found.add(code)
            if index >= max(0, len(lines) - 2):
                tail = re.search(r'(?<![a-z])(?:h\.?\s?k\.?|kln|u\.?\s?k\.?)\s*[,.]*$', line)
                if tail:
                    code = 'GB' if tail[0].startswith('u') else 'HK'
                    if code in self.catalogue.entries:
                        found.add(code)
            spans = []
            for code, alias, pattern in self._names:
                for match in pattern.finditer(line):
                    if any(left <= match.start() and right >= match.end() for left, right in spans):
                        continue
                    remainder = line[match.end():].strip(' ,.;:/()-')
                    han = any('\u3400' <= char <= '\u9fff' for char in alias)
                    if index == 0 and len(lines) > 1 and not _ADDRESS.search(line):
                        if line.strip(' ,.;:/()-') != alias:
                            continue
                    if not han and remainder and not re.fullmatch(r'[0-9\s-]+', remainder):
                        continue
                    found.add(code)
                    spans.append(match.span())
        return found

    def _infer(self, text, hint):
        lines = [unicodedata.normalize('NFKC', value).casefold().strip()
                 for value in text.splitlines() if value.strip()]
        if not lines and not hint:
            return (None, 'UNRESOLVED', 'EMPTY_ADDRESS', (), ())
        explicit = self._explicit(lines)
        if hint:
            hint_key = normalize_key(hint)
            if hint_key.upper() in self.catalogue.entries:
                explicit.add(hint_key.upper())
            else:
                explicit.update(self._explicit([hint_key]))
        if len(explicit) > 1:
            return (None, 'UNRESOLVED', 'CONFLICTING_COUNTRIES', (), tuple(sorted(explicit)))
        if explicit:
            return (next(iter(explicit)), 'DETERMINED', 'EXPLICIT_COUNTRY', (), ())

        # The first line remains available when it is geographic; a recipient
        # or business name is not allowed to supply regional evidence alone.
        address_lines = [line for _i, line in self._eligible_lines(lines)]
        scope = '\n'.join(address_lines)
        cn = _regional_match(scope, CN_REGIONS)
        hk = _regional_match(scope, HK_AREAS)
        if cn and hk:
            return (None, 'UNRESOLVED', 'CONFLICTING_ADMINISTRATIVE_REGIONS', (), ('CN', 'HK'))
        if cn and 'CN' in self.catalogue.entries:
            return ('CN', 'INFERRED', 'MAINLAND_ADMINISTRATIVE_REGION', (), ())
        if hk and 'HK' in self.catalogue.entries:
            return ('HK', 'INFERRED', 'HONG_KONG_LOCALITY', (), ())
        if not scope or not (_ADDRESS.search(scope) or len(lines) > 1):
            return (None, 'UNRESOLVED', 'NO_ADDRESS_CONTEXT', (), ())
        try:
            candidates = retrieve_candidates(self.geo_db, normalize_address(scope))
        except OccurrenceLimitExceeded:
            return (None, 'UNRESOLVED', 'GEOGRAPHIC_OCCURRENCE_LIMIT', (), ())
        candidates = self._substantial_candidates(candidates)
        grouped = {}
        for candidate in candidates:
            code = self.catalogue.geo_to_code.get(candidate.destination_id)
            if code not in self.catalogue.entries:
                continue
            if code not in grouped or candidate.support > grouped[code].support:
                grouped[code] = candidate
        ordered = sorted(grouped, key=lambda code: (-grouped[code].support, code))
        if not ordered:
            return (None, 'UNRESOLVED', 'NO_GEOGRAPHIC_MATCH', (), ())
        leader = ordered[0]
        if len(ordered) > 1 and grouped[ordered[1]].support >= grouped[leader].support * RIVAL_RATIO:
            return (None, 'UNRESOLVED', 'MULTIPLE_PLAUSIBLE_COUNTRIES', (), tuple(ordered[:5]))
        return (leader, 'INFERRED', 'GEOGRAPHIC_LEADER', (), tuple(ordered[:5]))

    def _substantial_candidates(self, candidates):
        if not candidates:
            return []
        ids = {int(item.split(':', 2)[1]) for c in candidates for item in c.evidence
               if item.startswith('PLACE:')}
        if not ids:
            return []
        if self._db is None:
            self._db = sqlite3.connect(self.geo_db.resolve().as_uri() + '?mode=ro', uri=True)
            self._db.execute('PRAGMA query_only=ON')
        qualified = set()
        values = sorted(ids)
        for start in range(0, len(values), 200):
            chunk = values[start:start + 200]
            rows = self._db.execute(
                'SELECT country_code,feature_code,population FROM geo_places '
                'WHERE place_id IN (' + ','.join('?' * len(chunk)) + ')', chunk)
            for country, feature, population in rows:
                if feature in {'PCLI', 'PCLX', 'PCLS', 'PCLD', 'ADM1', 'ADM2', 'PPLC', 'PPLA'} or (population or 0) >= 100_000:
                    qualified.add(country)
        return [c for c in candidates if c.destination_id in qualified and c.support >= 0.15]
